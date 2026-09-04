"""Проверка задания на AI-персонах: снимок → движок → рекомендации.

Чистая часть (перевод критериев, разбор находок, сводка) отделена от адаптеров
к БД и движку — её и проверяют тесты, без постгреса и без сети.

Два принципа, ради которых всё и написано:

* **Один прогон — один тип персон.** AI-студенты проверяют, понятна ли
  постановка; AI-ревьюеры — однозначны ли критерии. Смешивать нечего: это
  разные вопросы с разными выводами.
* **AI ничего не переписывает молча.** Прогон отдаёт рекомендации, каждую
  человек применяет, правит или отклоняет. Повторный прогон — только явным
  действием: изменение задания само по себе ничего не запускает.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import AiRecommendation, AiRun, Assignment, RubricVersion
from .taskcreater_client import TaskCreaterClient, TaskCreaterError

log = logging.getLogger(__name__)

PERSONA_TYPES = ("student", "reviewer")
OPEN_STATUSES = ("queued", "running")

# Важность в терминах ТЗ. Движок мыслит severity агента, кабинет — тем, насколько
# срочно методисту это чинить.
SEVERITY = {"high": "critical", "medium": "important", "low": "improvement"}

# Куда чинится находка «по брифу». Правку критерия движок отдаёт машинной формой,
# а находке по заданию машинной формы нет — целевой блок выбирается здесь и явно,
# чтобы «Применить» знало, в какое поле класть текст.
BRIEF_FIELDS = {
    "leaky_public": "student_hint",
    "scope_creep": "statement",
    "unfair_hidden": "statement",
}
FIELD_TITLES = {
    "statement": "Условие задания",
    "context": "Контекст",
    "expected_result": "Ожидаемый результат",
    "constraints": "Ограничения",
    "student_hint": "Подсказка студенту",
}

# Блоки, которые редактор задания отдаёт движку как контекст задания.
AUTHORING_FIELDS = (
    "topic",
    "difficulty",
    "estimated_minutes",
    "learning_objectives",
    "context",
    "expected_result",
    "constraints",
    "submission_format",
    "materials",
    "reviewer_notes",
    "reference_solution",
)


# --------------------------------------------------------------------------- #
#  Критерий: кабинет ↔ движок
# --------------------------------------------------------------------------- #


def to_engine_criterion(criterion: dict) -> dict:
    """Критерий кабинета в форме движка.

    У кабинета критерий может быть заполнен наполовину (методист завёл название
    и вес), а движок требует описание и подсказку, куда смотреть. Пустое место
    заполняем названием, а не выдумкой: агент увидит ровно то, что есть.
    """

    title = str(criterion.get("title") or "").strip()
    return {
        "key": str(criterion.get("key") or "").strip() or "criterion",
        "title": title,
        "max_points": float(criterion.get("max_score") or criterion.get("max_points") or 1),
        "student_hint": criterion.get("student_hint") or "",
        "description": criterion.get("description") or title,
        "check_kind": criterion.get("check_kind") or "subjective",
        "evidence_hint": criterion.get("evidence_hint") or "—",
        "expected_signals": list(criterion.get("expected_signals") or []),
        "rubric_levels": list(criterion.get("rubric_levels") or []),
    }


def from_engine_criterion(criterion: dict) -> dict:
    """Критерий движка в форме кабинета: балл называется max_score."""

    return {
        "key": criterion.get("key") or "criterion",
        "title": criterion.get("title") or "",
        "max_score": float(criterion.get("max_points") or 1),
        "student_hint": criterion.get("student_hint") or "",
        "description": criterion.get("description") or "",
        "check_kind": criterion.get("check_kind") or "subjective",
        "evidence_hint": criterion.get("evidence_hint") or "",
        "expected_signals": list(criterion.get("expected_signals") or []),
        "rubric_levels": list(criterion.get("rubric_levels") or []),
    }


def engine_payload(*, title: str, statement: str, authoring: dict, criteria: list[dict]) -> dict:
    """Неизменяемый снимок задания для прогона.

    Снимок собирается один раз на запуск и дальше не меняется: правка черновика
    во время прогона не должна задним числом менять то, что проверяли.
    """

    authoring = authoring or {}
    return {
        "title": title or "Без названия",
        "track": authoring.get("topic") or "General",
        "context_md": authoring.get("context") or "",
        "statement_md": statement or title or "",
        "deliverables": list(authoring.get("deliverables") or []),
        "submission_format": authoring.get("submission_format") or "",
        "learning_objectives": list(authoring.get("learning_objectives") or []),
        "criteria": [to_engine_criterion(item) for item in criteria],
        "reference_solution_md": authoring.get("reference_solution") or "",
        "reviewer_notes": authoring.get("reviewer_notes") or "",
    }


def draft_from_engine_task(task: dict, *, track: str = "", total_points: float = 10) -> dict:
    """Сгенерированное движком задание в форме черновика кабинета.

    Это предпросмотр, а не запись: поля едут на экран, и что из них оставить,
    решает методист.
    """

    data = task.get("data") or {}
    deliverables = list(data.get("deliverables") or [])
    return {
        "title": data.get("title", ""),
        "statement": data.get("statement_md", ""),
        "authoring": {
            "topic": track or data.get("track") or "",
            "context": data.get("context_md", ""),
            "expected_result": "\n".join(f"• {item}" for item in deliverables),
            "learning_objectives": data.get("learning_objectives") or [],
            "reference_solution": data.get("reference_solution_md", ""),
            "reviewer_notes": data.get("reviewer_notes", ""),
        },
        "criteria": [from_engine_criterion(item) for item in data.get("criteria") or []],
        "pass_score": round(float(task.get("total_points") or total_points) * 0.6, 1),
    }


# --------------------------------------------------------------------------- #
#  Результат движка → рекомендации
# --------------------------------------------------------------------------- #


def _criterion_text(criterion: dict | None) -> str:
    """Человекочитаемая форма критерия — то, что методист увидит в diff'е."""

    if not criterion:
        return ""
    lines = [str(criterion.get("description") or criterion.get("title") or "").strip()]
    signals = [s for s in (criterion.get("expected_signals") or []) if s]
    if signals:
        lines.append("Признаки сильного ответа: " + "; ".join(str(s) for s in signals))
    levels = criterion.get("rubric_levels") or []
    if levels:
        lines.append(
            "Уровни: "
            + "; ".join(f"{lv.get('points')} — {lv.get('label')}" for lv in levels if lv)
        )
    return "\n".join(line for line in lines if line)


def _evidence(finding: dict) -> list[str]:
    return [str(finding.get("evidence") or "").strip()] if finding.get("evidence") else []


def recommendations_from_result(
    result: dict,
    persona_type: str,
    *,
    criteria: list[dict] | None = None,
) -> list[dict]:
    """Рекомендации по итогам прогона — по одной на предложенное изменение.

    Прогон на ревьюерах правит критерии: движок отдаёт готовую правку целиком,
    её и предлагаем. Прогон на студентах правит бриф: машинной формы у такой
    находки нет, поэтому текст замены дописывается отдельно (`enrich_proposals`),
    а пока едет пустым — экран тогда предложит отредактировать вручную.
    """

    by_key = {c.get("key"): c for c in (criteria or [])}
    rows: list[dict] = []

    if persona_type == "reviewer":
        for edit in result.get("proposed_edits") or []:
            proposed = edit.get("proposed_criterion")
            key = edit.get("criterion_key") or ""
            rows.append(
                {
                    "target_type": "criterion",
                    "target_id": key,
                    "target_field": edit.get("operation") or "modify",
                    "severity": SEVERITY.get(edit.get("severity"), "improvement"),
                    "problem": edit.get("rationale") or "",
                    "evidence": list(edit.get("addresses") or []),
                    "original_value": edit.get("before_snapshot")
                    or _criterion_text(by_key.get(key)),
                    "proposed_value": _criterion_text(proposed),
                    "expected_effect": "Критерий станет применяться однозначно.",
                    "payload": edit,
                }
            )

    # Находки без машинной правки: по заданию — всегда, по рубрике — только те,
    # что критик не закрыл правкой (иначе одно и то же приедет дважды).
    covered = {addr for edit in (result.get("proposed_edits") or []) for addr in (edit.get("addresses") or [])}
    for finding in result.get("open_findings") or []:
        is_brief = finding.get("target") == "brief"
        if persona_type == "student" and not is_brief:
            continue
        if persona_type == "reviewer" and (is_brief or finding.get("id") in covered):
            continue
        key = finding.get("criterion_key")
        field = BRIEF_FIELDS.get(finding.get("kind"), "statement")
        on_criterion = field == "student_hint" and key
        rows.append(
            {
                "target_type": "criterion" if on_criterion else "task_field",
                "target_id": key if on_criterion else None,
                "target_field": field if on_criterion else ("statement" if is_brief else "criteria"),
                "severity": SEVERITY.get(finding.get("severity"), "improvement"),
                "problem": finding.get("explanation") or "",
                "evidence": _evidence(finding),
                "original_value": "",
                "proposed_value": "",
                "expected_effect": finding.get("fix_suggestion") or "",
                "payload": {"finding": finding},
            }
        )

    for position, row in enumerate(rows):
        row["position"] = position
    return rows


def persona_cards(result: dict, persona_type: str) -> list[dict]:
    """Карточки персон последнего раунда.

    Вёрстка не знает, сколько персон вернёт движок, и знать не должна: набор
    профилей задаётся конфигом прогона и меняется без правки экрана.
    """

    rounds = result.get("rounds") or []
    if not rounds:
        return []
    last = rounds[-1]
    if persona_type == "student":
        return [
            {
                "key": item.get("persona"),
                "understood": not item.get("exploited_ambiguities"),
                "approach": item.get("approach_notes") or "",
                "troubles": list(item.get("exploited_ambiguities") or []),
            }
            for item in last.get("solutions") or []
        ]
    return [
        {
            "key": item.get("persona"),
            "total_points": item.get("total_points"),
            "comment": item.get("overall_comment") or "",
            "undecidable": [
                s.get("criterion_key")
                for s in item.get("scores") or []
                if not s.get("decidable")
            ],
        }
        for item in last.get("gradings") or []
    ]


def score_spread(result: dict) -> list[dict]:
    """Разброс оценок по критериям — чем он шире, тем хуже читается критерий."""

    rounds = result.get("rounds") or []
    if not rounds:
        return []
    rows = []
    for key, per_persona in (rounds[-1].get("score_matrix") or {}).items():
        values = [v for v in per_persona.values() if v is not None]
        if not values:
            continue
        rows.append(
            {
                "criterion_key": key,
                "min": min(values),
                "max": max(values),
                "spread": round(max(values) - min(values), 2),
                "by_persona": per_persona,
            }
        )
    return sorted(rows, key=lambda r: -r["spread"])


def run_summary(result: dict, persona_type: str, recommendations: list[dict]) -> dict:
    """Верхнее резюме прогона: что прошло хорошо, что нет, насколько критично.

    Голый «балл качества» здесь не считается намеренно: одно число без разбора
    не говорит методисту, что чинить.
    """

    counts = {"critical": 0, "important": 0, "improvement": 0}
    for row in recommendations:
        counts[row["severity"]] = counts.get(row["severity"], 0) + 1
    rounds = result.get("rounds") or []
    solutions = len(rounds[0].get("solutions") or []) if rounds else 0
    understood = sum(1 for card in persona_cards(result, "student") if card["understood"])
    wide = [row for row in score_spread(result) if row["spread"] >= 1]

    if persona_type == "student":
        good = f"Постановку поняли без догадок: {understood} из {solutions}."
        headline = (
            "Задание читается однозначно."
            if not recommendations
            else f"Есть места, где студенты поймут задание по-разному: {len(recommendations)}."
        )
    else:
        good = (
            "Оценки сошлись по всем критериям."
            if not wide
            else f"Критериев с широким разбросом оценок: {len(wide)}."
        )
        headline = (
            "Критерии применяются однозначно."
            if not recommendations
            else f"Критерии стоит доработать: предложено правок — {len(recommendations)}."
        )

    return {
        "verdict": "ok" if not recommendations else "attention",
        "headline": headline,
        "good": good,
        "counts": counts,
        "recommendations": len(recommendations),
        "converged": bool(result.get("converged")),
        "solutions": solutions,
        "note": result.get("summary") or "",
    }


# --------------------------------------------------------------------------- #
#  Применение рекомендации к критериям (чистая функция)
# --------------------------------------------------------------------------- #


def criteria_after(criteria: list[dict], edit: dict, value: str) -> list[dict]:
    """Критерии после применения одной правки.

    `value` — то, что человек в итоге подтвердил: если он отредактировал
    предложение, в критерий едет его текст, а не исходное предложение агента.
    """

    operation = edit.get("operation")
    key = edit.get("criterion_key")
    proposed = edit.get("proposed_criterion")
    rows = [dict(item) for item in criteria]

    if operation == "remove":
        return [item for item in rows if item.get("key") != key]
    if not proposed:
        return rows

    updated = from_engine_criterion(proposed)
    if value:
        updated["description"] = value
    for index, item in enumerate(rows):
        if item.get("key") == key:
            rows[index] = {**item, **updated, "key": item.get("key")}
            return rows
    rows.append(updated)
    return rows


# --------------------------------------------------------------------------- #
#  Адаптеры: БД и движок
# --------------------------------------------------------------------------- #


def client() -> TaskCreaterClient:
    """Единственная точка создания клиента движка — её и подменяют тесты."""

    return TaskCreaterClient()


def current_revision(db: Session, assignment: Assignment) -> int:
    rubric = db.get(RubricVersion, assignment.current_rubric_version_id)
    return rubric.version if rubric else 0


def reusable_run(db: Session, assignment_id: UUID, idempotency_key: str | None) -> AiRun | None:
    """Прогон, который уже отвечает на этот же запрос.

    Двойной клик по «Запустить проверку» — это один запрос, а не два прогона.
    Без ключа идемпотентности гейтом служит сам факт незавершённого прогона.
    """

    query = select(AiRun).where(AiRun.assignment_id == assignment_id)
    if idempotency_key:
        return db.scalars(query.where(AiRun.idempotency_key == idempotency_key)).first()
    return db.scalars(
        query.where(AiRun.status.in_(OPEN_STATUSES)).order_by(AiRun.created_at.desc())
    ).first()


def _running_since(run: AiRun) -> datetime:
    stamp = run.created_at or datetime.now(UTC)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def is_stale(run: AiRun, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    limit = timedelta(seconds=settings.ai_task_run_stale_after_seconds)
    return run.status in OPEN_STATUSES and now - _running_since(run) > limit


def recover_orphaned_runs() -> int:
    """Прогоны живут в BackgroundTasks процесса и не переживают его перезапуск.

    Всё, что осталось в queued/running от прошлого процесса, уже никогда не
    завершится: помечаем провалом, иначе запись висит вечно и её нельзя ни
    перезапустить, ни закрыть.
    """

    with SessionLocal() as db:
        rows = list(db.scalars(select(AiRun).where(AiRun.status.in_(OPEN_STATUSES))))
        for run in rows:
            run.status = "failed"
            run.error = "Прогон прерван перезапуском сервиса. Запустите проверку заново."
            run.completed_at = datetime.now(UTC)
        db.commit()
        return len(rows)


def create_run(
    db: Session,
    assignment: Assignment,
    *,
    persona_type: str,
    idempotency_key: str | None,
    created_by: UUID | None,
) -> AiRun:
    run = AiRun(
        assignment_id=assignment.id,
        revision=current_revision(db, assignment),
        persona_type=persona_type,
        status="queued",
        progress="поставлен в очередь",
        idempotency_key=idempotency_key,
        created_by=created_by,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _fail(run_id: UUID, message: str) -> None:
    with SessionLocal() as db:
        run = db.get(AiRun, run_id)
        if not run:
            return
        run.status = "failed"
        run.error = message
        run.completed_at = datetime.now(UTC)
        db.commit()


def _progress(run_id: UUID, text: str, **fields) -> None:
    with SessionLocal() as db:
        run = db.get(AiRun, run_id)
        if not run:
            return
        run.progress = text
        for name, value in fields.items():
            setattr(run, name, value)
        db.commit()


def enrich_proposals(client: TaskCreaterClient, rows: list[dict], context: dict, limit: int = 6) -> None:
    """Дописывает текст замены там, где движок отдал только совет.

    Находка по заданию приходит советом «что поменять», а «Применить» должно
    класть в поле готовый текст. Просим движок переписать блок под этот совет —
    один вызов на находку. Не вышло — рекомендация остаётся без предложения, и
    экран предложит отредактировать вручную; терять находку из-за этого нельзя.
    """

    done = 0
    for row in rows:
        if row["proposed_value"] or done >= limit:
            continue
        field = row["target_field"]
        current = context.get(field, "")
        try:
            out = client.assist_field(
                field=FIELD_TITLES.get(field, field),
                mode="improve" if current else "fill",
                current=current,
                instruction=f"{row['problem']} {row['expected_effect']}".strip(),
                context={k: v for k, v in context.items() if k != field},
            )
        except TaskCreaterError as exc:
            log.warning("task_ai: не удалось собрать замену для %s: %s", field, exc)
            continue
        row["proposed_value"] = out.get("proposed") or ""
        row["original_value"] = current
        done += 1


def execute_run(run_id: UUID) -> None:
    """Фоновый прогон целиком. Исключения наружу не выпускает."""

    with SessionLocal() as db:
        run = db.get(AiRun, run_id)
        if not run or run.status != "queued":
            return
        assignment = db.get(Assignment, run.assignment_id)
        if not assignment:
            return
        rubric = db.get(RubricVersion, assignment.current_rubric_version_id)
        persona_type = run.persona_type
        payload = engine_payload(
            title=assignment.title,
            statement=assignment.statement,
            authoring=assignment.authoring or {},
            criteria=rubric.criteria if rubric else [],
        )
        context = {
            "title": assignment.title,
            "statement": assignment.statement,
            **{k: v for k, v in (assignment.authoring or {}).items() if isinstance(v, str)},
        }
        run.status = "running"
        run.progress = "готовим снимок задания"
        db.commit()

    engine = client()
    try:
        imported = engine.import_task(payload)
        _progress(run_id, "запускаем персон", external_task_id=imported.get("id"))
        started = engine.start_validation(imported["id"], persona_type=persona_type)
        external_run_id = started["id"]
        _progress(run_id, started.get("progress") or "прогон идёт", external_run_id=external_run_id)

        deadline = time.monotonic() + settings.ai_task_run_timeout_seconds
        state = started
        while time.monotonic() < deadline:
            time.sleep(settings.ai_task_run_poll_seconds)
            state = engine.get_run(external_run_id)
            if state["status"] in ("succeeded", "failed"):
                break
            _progress(run_id, state.get("progress") or "прогон идёт")
        else:
            _fail(run_id, "Прогон не завершился за отведённое время")
            return

        if state["status"] == "failed" or not state.get("result"):
            _fail(run_id, state.get("error") or "Движок не вернул результат")
            return

        result = state["result"]
        rows = recommendations_from_result(result, persona_type, criteria=payload["criteria"])
        enrich_proposals(engine, rows, context)
    except TaskCreaterError as exc:
        _fail(run_id, str(exc))
        return
    except Exception as exc:  # фоновая задача не должна падать молча
        log.exception("task_ai: прогон %s упал", run_id)
        _fail(run_id, f"Внутренняя ошибка прогона: {exc}")
        return

    with SessionLocal() as db:
        run = db.get(AiRun, run_id)
        if not run:
            return
        for row in rows:
            db.add(AiRecommendation(run_id=run.id, **row))
        run.summary = run_summary(result, persona_type, rows)
        run.personas = persona_cards(result, persona_type)
        run.metrics = result.get("metrics") or {}
        run.status = "completed"
        run.progress = "готово"
        run.completed_at = datetime.now(UTC)
        db.commit()


def start(db: Session, run: AiRun, background_tasks) -> None:
    """Ставит прогон в фон. Отдельной функцией — чтобы тесты глушили одну точку."""

    del db
    background_tasks.add_task(execute_run, run.id)
