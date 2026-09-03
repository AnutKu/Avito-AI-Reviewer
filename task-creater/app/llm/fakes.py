"""Оффлайн-режим (TASKCREATER_LLM_FAKE=1): детерминированные ответы вместо вызовов LLM.

Нужен для тестов и для демонстрации сквозного сценария без доступа к шлюзу.
Ответы не «умные», но структурно валидные и связные: генератор кладёт в рубрику
пару заведомо проблемных критериев, решатели расходятся в самооценке, грейдер
отмечает неоднозначность, критик находит её и предлагает правку. На втором раунде
(в критериях появляется маркер «[уточнено]») критик отдаёт converged=true.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_MARK = re.compile(r"<(?P<tag>[A-Z_]+)>(?P<body>.*?)</(?P=tag)>", re.DOTALL)


def _tag(text: str, name: str) -> str | None:
    for m in _MARK.finditer(text):
        if m.group("tag") == name:
            return m.group("body").strip()
    return None


def _criteria_from_prompt(text: str) -> list[dict]:
    raw = _tag(text, "CRITERIA_JSON")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _stable_frac(*parts: str) -> float:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


# --------------------------------------------------------------------------- #
#  Построители фейковых объектов по имени схемы
# --------------------------------------------------------------------------- #


def _fake_generated_task(system: str, user: str):
    from app.schemas import Criterion, GeneratedTask, RubricLevel

    idea = _tag(user, "IDEA") or "учебное задание"
    track = _tag(user, "TRACK") or "General"
    total = float(_tag(user, "TOTAL_POINTS") or 10)

    criteria = [
        Criterion(
            key="functional-correctness",
            title="Функциональная корректность",
            student_hint="Все пункты задания выполнены и работают как описано",
            description="Все требования условия выполнены: перечисленные артефакты присутствуют "
            "и ведут себя как описано, крайние случаи обработаны.",
            max_points=round(total * 0.4, 2),
            check_kind="objective",
            evidence_hint="Сверить список требований условия с реализацией пункт за пунктом",
            expected_signals=[
                "Каждый пункт условия закрыт явно",
                "Крайние случаи из условия обработаны и это видно в решении",
            ],
            rubric_levels=[
                RubricLevel(points=0, label="не выполнено", descriptor="ключевые требования отсутствуют"),
                RubricLevel(
                    points=round(total * 0.2, 2),
                    label="частично",
                    descriptor="есть пропуски или необработанные случаи",
                ),
                RubricLevel(
                    points=round(total * 0.4, 2),
                    label="полностью",
                    descriptor="все требования и крайние случаи покрыты",
                ),
            ],
        ),
        Criterion(
            key="test-coverage",
            title="Тесты",
            student_hint="Решение покрыто тестами",
            description="Решение покрыто тестами в достаточном объёме.",
            max_points=round(total * 0.25, 2),
            check_kind="objective",
            evidence_hint="Посмотреть каталог с тестами",
            expected_signals=[
                "Не менее 8 осмысленных тест-кейсов",
                "Минимум 3 теста на крайние случаи и ошибки",
            ],
            rubric_levels=[],
        ),
        Criterion(
            key="readable-code",
            title="Читаемость",
            student_hint="Оформление и читаемость",
            description="Код человекочитаемый и написан в хорошем стиле, как на воркшопе.",
            max_points=round(total * 0.2, 2),
            check_kind="subjective",
            evidence_hint="Бегло просмотреть основные файлы",
            expected_signals=[],
            rubric_levels=[],
        ),
        Criterion(
            key="architecture",
            title="Структура",
            student_hint="Структура решения",
            description="Решение разбито на части с понятными границами, структура соответствует условию.",
            max_points=round(total * 0.15, 2),
            check_kind="subjective",
            evidence_hint="Оценить декомпозицию и границы модулей",
            expected_signals=[],
            rubric_levels=[],
        ),
    ]
    return GeneratedTask(
        title=f"[demo] {idea[:60]}",
        summary=f"Учебное задание по направлению «{track}»: {idea[:120]}",
        context_md=f"Направление: {track}. (Оффлайн-режим — контекст демонстрационный.)",
        statement_md=(
            f"## Задача\n\n{idea}\n\n"
            "> Сгенерировано в оффлайн-режиме (fake LLM) — форма реальная, содержание демонстрационное."
        ),
        deliverables=[
            "Реализуйте описанное решение",
            "Покройте решение тестами",
            "Оформите структуру и опишите ключевые решения",
        ],
        submission_format="Ссылка на репозиторий / документ с решением.",
        public_rubric_note="Максимум 10 баллов, по критериям из таблицы. "
        "По каждому: полный балл — сделано и обосновано, половина — есть пробелы, 0 — нет.",
        learning_objectives=[
            f"Освоить базовые практики направления «{track}»",
            "Научиться декомпозировать требования и покрывать их тестами",
        ],
        criteria=criteria,
        reference_solution_md="## Эталон\n\nРеференсное решение: все требования выполнены, "
        "тесты покрывают основные и крайние случаи, решение разбито на части.",
        common_mistakes=[
            "Не обработаны крайние случаи из условия",
            "Тесты проверяют только happy-path",
            "Вся логика в одном месте",
        ],
        reviewer_notes="Спорные места: границы «достаточного объёма тестов» и «хорошего стиля» "
        "калибруются на встрече ревьюеров.",
    )


def _fake_solver_output(system: str, user: str):
    from app.schemas import SelfCriterionScore, SolverOutput

    persona = _tag(user, "PERSONA") or _tag(system, "PERSONA") or "diligent_strong"
    criteria = _criteria_from_prompt(user)

    profile = {
        "diligent_strong": 0.9,
        "minimalist_weak": 0.45,
        "rule_lawyer": 0.8,
        "ambiguity_prober": 0.6,
    }.get(persona, 0.7)

    self_scores: list[SelfCriterionScore] = []
    exploited: list[str] = []
    for c in criteria:
        key = c.get("key", "unknown")
        mx = float(c.get("max_points", 1))
        jitter = _stable_frac(persona, key)
        frac = min(1.0, max(0.0, profile + (jitter - 0.5) * 0.5))
        # «Юрист правил» и «исследователь неоднозначности» вытягивают балл именно
        # на нечётких критериях.
        if c.get("check_kind") == "subjective" and persona in {"rule_lawyer", "ambiguity_prober"}:
            frac = 0.95
            exploited.append(f"{key}: формулировка не задаёт измеримого порога — трактую её в свою пользу")
        if key == "test-coverage" and persona == "rule_lawyer":
            frac = 1.0
            exploited.append("test-coverage: «достаточный объём» не задан числом — добавил 1 тест-заглушку")
        self_scores.append(
            SelfCriterionScore(
                criterion_key=key,
                expected_points=round(mx * frac, 2),
                reasoning=f"[{persona}] самооценка по критерию «{c.get('title', key)}»",
            )
        )

    return SolverOutput(
        persona=persona,
        approach_notes=f"[{persona}] Прочитал условие, выделил требования, реализовал их "
        f"{'аккуратно и с тестами' if profile > 0.7 else 'по минимуму'}.",
        solution_md=f"```\n// решение профиля {persona}\n// (оффлайн-режим: демонстрационное)\n```",
        self_assessment=self_scores,
        exploited_ambiguities=exploited,
    )


def _fake_grader_output(system: str, user: str):
    from app.schemas import GradedCriterion, GraderOutput

    persona = _tag(user, "PERSONA") or "unknown"
    criteria = _criteria_from_prompt(user)
    scores: list[GradedCriterion] = []
    total = 0.0
    for c in criteria:
        key = c.get("key", "unknown")
        mx = float(c.get("max_points", 1))
        jitter = _stable_frac("grade", persona, key)
        # Пока критерий не уточнён — субъективные оценки «плавают» и часто недекларируемы.
        if c.get("check_kind") == "subjective" and "[уточнено]" not in c.get("description", ""):
            pts = round(mx * (0.4 + jitter * 0.6), 2)
            decidable = False
            note = "нет измеримого признака: понятия «читаемость»/«хороший стиль» не формализованы"
        else:
            pts = round(mx * (0.55 + jitter * 0.4), 2)
            decidable = True
            note = None
        total += pts
        scores.append(
            GradedCriterion(
                criterion_key=key,
                points=pts,
                max_points=mx,
                rationale=f"Оценка критерия «{c.get('title', key)}» для решения профиля {persona}.",
                evidence_quote="// демонстрационная цитата из решения",
                confidence=round(0.9 if decidable else 0.5 + jitter * 0.2, 2),
                decidable=decidable,
                ambiguity_note=note,
            )
        )
    return GraderOutput(
        persona=persona,
        scores=scores,
        total_points=round(total, 2),
        overall_comment=f"Предварительная оценка решения профиля {persona} (оффлайн-режим).",
    )


def _fake_critic_output(system: str, user: str):
    from app.schemas import Criterion, CriterionEdit, CriticOutput, Finding

    criteria = _criteria_from_prompt(user)
    already_refined = any("[уточнено]" in c.get("description", "") for c in criteria)

    if already_refined:
        return CriticOutput(
            findings=[],
            proposed_edits=[],
            converged=True,
            convergence_reason="После уточнения формулировок расхождения оценок между профилями "
            "в пределах нормы, недекларируемых критериев не осталось.",
        )

    findings = [
        Finding(
            id="F1",
            criterion_key="readable-code",
            kind="unmeasurable",
            severity="high",
            target="rubric",
            explanation="«Человекочитаемый код / хороший стиль как на воркшопе» — субъективное "
            "понятие без наблюдаемых признаков и порога баллов.",
            fix_suggestion="Заменить на чек-лист нарушений с порогами баллов.",
            evidence="Грейдер пометил decidable=false по всем решениям; профили rule_lawyer и "
            "ambiguity_prober получили почти максимум, хотя качество решений разное.",
        ),
        Finding(
            id="F2",
            criterion_key="test-coverage",
            kind="gameable",
            severity="medium",
            target="rubric",
            explanation="«Достаточный объём тестов» не задан числом — критерий выполняется "
            "формально одним тестом-заглушкой.",
            fix_suggestion="Ввести измеримый порог: ≥8 осмысленных кейсов, из них ≥3 на крайние случаи.",
            evidence="Профиль rule_lawyer выставил себе полный балл за 1 тест.",
        ),
        Finding(
            id="F3",
            criterion_key=None,
            kind="overlapping",
            severity="low",
            target="rubric",
            explanation="Критерии readable-code и architecture частично пересекаются по признаку "
            "«структура/слои», возможен двойной учёт.",
            fix_suggestion="Развести: readable-code — локальный стиль, architecture — границы модулей.",
            evidence="Грейдер ссылается на одни и те же места в обоснованиях обоих критериев.",
        ),
        Finding(
            id="F4",
            criterion_key="test-coverage",
            kind="unfair_hidden",
            severity="medium",
            target="brief",
            explanation="Скрытые expected_signals требуют «≥8 кейсов, ≥3 на крайние случаи», но в "
            "брифе студенту сказано только «покройте решение тестами» — это нельзя вывести.",
            fix_suggestion="Вынести минимальные требования к тестам в пункт сдачи (deliverables) "
            "или в public_rubric_note.",
            evidence="minimalist_weak написал 1 тест и «не мог знать» про порог; в брифе порога нет.",
        ),
    ]

    def refined(key: str, title: str, desc: str, mx: float, kind: str, hint: str) -> Criterion:
        return Criterion(
            key=key,
            title=title,
            student_hint=f"{title.lower()} — по чек-листу",
            description=desc + " [уточнено]",
            max_points=mx,
            check_kind=kind,
            evidence_hint=hint,
            expected_signals=["Проверяемый порог задан числом", "Формальное выполнение не засчитывается"],
            rubric_levels=[],
        )

    src = {c["key"]: c for c in criteria if "key" in c}
    edits = [
        CriterionEdit(
            id="E1",
            operation="modify",
            criterion_key="readable-code",
            before_snapshot=src.get("readable-code", {}).get("description"),
            proposed_criterion=refined(
                "readable-code",
                "Читаемость кода",
                "Именование сущностей отражает их роль; функции ≤ ~40 строк; нет закомментированного "
                "кода и магических чисел; ошибки обрабатываются явно. Полный балл — если нарушений ≤2, "
                "половина — 3–5, ноль — >5.",
                float(src.get("readable-code", {}).get("max_points", 2)),
                "objective",
                "Просмотреть 3–4 основных файла, отметить нарушения по чек-листу",
            ),
            rationale="Заменяем субъективное понятие наблюдаемым чек-листом с порогами баллов.",
            addresses=["F1"],
            severity="high",
        ),
        CriterionEdit(
            id="E2",
            operation="modify",
            criterion_key="test-coverage",
            before_snapshot=src.get("test-coverage", {}).get("description"),
            proposed_criterion=refined(
                "test-coverage",
                "Тесты",
                "Не менее 8 осмысленных тест-кейсов, среди них хотя бы 3 — на крайние случаи и "
                "ошибки из условия. Тесты-заглушки без проверок не засчитываются.",
                float(src.get("test-coverage", {}).get("max_points", 2.5)),
                "objective",
                "Открыть тесты, пересчитать осмысленные кейсы и покрытие крайних случаев",
            ),
            rationale="Вводим измеримый порог и явно исключаем формальное выполнение.",
            addresses=["F2"],
            severity="medium",
        ),
    ]
    return CriticOutput(
        findings=findings,
        proposed_edits=edits,
        converged=False,
        convergence_reason="Есть находки severity>=medium — рубрика требует уточнения.",
    )


_BUILDERS = {
    "GeneratedTask": _fake_generated_task,
    "SolverOutput": _fake_solver_output,
    "GraderOutput": _fake_grader_output,
    "CriticOutput": _fake_critic_output,
}


def fake_structured(schema: type[T], *, system: str, user: str) -> T:
    builder = _BUILDERS.get(schema.__name__)
    if builder is None:  # pragma: no cover — защ. от новых схем
        raise NotImplementedError(f"нет fake-построителя для схемы {schema.__name__}")
    return builder(system, user)
