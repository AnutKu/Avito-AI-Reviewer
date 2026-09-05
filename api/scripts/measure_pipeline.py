"""Замер: сколько занимает и сколько стоит каждая автоматизированная операция.

    python -m scripts.measure_pipeline                 # всё, по 2 повтора
    python -m scripts.measure_pipeline --repeat 3
    python -m scripts.measure_pipeline --only review,distribution

Скрипт ничего не оценивает и не моделирует: он выполняет те же самые функции,
что и кабинет, засекает время и берёт токены из ответа провайдера. Поэтому он
стоит денег — ровно столько, сколько показывает в колонке «стоимость».

Ручные ориентиры («сколько это занимало у человека») лежат в
`app/services/effort.py` с указанием источника и сюда только подставляются.
Замер и ориентир не смешиваются: первое измерено сегодня, второе сказано на
интервью, и путать их нельзя.

Состояние базы скрипт возвращает как было: прогоны запускаются на копиях
записей, а разборы после замера восстанавливаются из репозитория.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AiStatus,
    Assignment,
    LlmCall,
    Review,
    Snapshot,
    Submission,
    SubmissionStatus,
)
from app.services import task_ai  # noqa: E402
from app.services.ai_reviewer_client import AiReviewerClient  # noqa: E402
from app.services.distribution import proposals, reviewer_loads  # noqa: E402
from app.services.effort import BASELINE_BY_OPERATION, cost_usd, saved_minutes  # noqa: E402
from app.services.review_pipeline import (  # noqa: E402
    blitz_questions_with_retries,
    run_detection,
    run_review,
)

REPORT = ROOT / "data" / "measurements.json"

# Что человек всё равно делает после машины. Без этой поправки экономия
# считается так, будто работу закрывает сам вызов модели.
HUMAN_AFTER_MINUTES = {
    "review": 12.5,          # ревьюер читает разбор и принимает решение по критериям
    "task_generate": 15.0,   # методист вычитывает и правит сгенерированное задание
}


class Measured:
    """Накопитель замеров одной операции."""

    def __init__(self, key: str, title: str, unit: str = "вызов"):
        self.key, self.title, self.unit = key, title, unit
        self.seconds: list[float] = []
        self.error: str | None = None

    def add(self, value: float) -> None:
        self.seconds.append(value)

    @property
    def median(self) -> float | None:
        return round(statistics.median(self.seconds), 4) if self.seconds else None

    @property
    def spread(self) -> str:
        if len(self.seconds) < 2:
            return ""
        low, high = min(self.seconds), max(self.seconds)
        if high < 1:
            return f"{low * 1000:.0f}–{high * 1000:.0f} мс"
        return f"{low:.1f}–{high:.1f} с"


def _sample_submission(db):
    return db.execute(
        select(Review, Submission, Snapshot)
        .join(Submission, Submission.id == Review.submission_id)
        .join(Snapshot, Snapshot.submission_id == Submission.id)
        .where(Review.ai_status == AiStatus.READY)
        .order_by(Submission.submitted_at)
    ).first()


# --------------------------------------------------------------------------- #
#  Операции
# --------------------------------------------------------------------------- #


def measure_review(db, repeat: int) -> Measured:
    out = Measured("review", "Проверка работы по критериям")
    row = _sample_submission(db)
    if row is None:
        out.error = "нет готовых работ — сначала загрузите курс"
        return out
    review, *_ = row
    for _ in range(repeat):
        review.ai_status = AiStatus.PENDING
        db.commit()
        started = time.monotonic()
        run_review(review.id)
        out.add(time.monotonic() - started)
        db.expire_all()
        review = db.get(Review, review.id)
    return out


def measure_blitz(db, repeat: int) -> Measured:
    out = Measured("blitz_questions", "Составить вопросы студенту")
    row = _sample_submission(db)
    if row is None:
        out.error = "нет работ"
        return out
    review, submission, snapshot = row
    for _ in range(repeat):
        started = time.monotonic()
        response = blitz_questions_with_retries(
            assignment=submission.assignment, snapshot=snapshot, count=3, focus=[]
        )
        out.add(time.monotonic() - started)
        _remember(db, review.id, "blitz_questions", response.metadata, out.seconds[-1])
    return out


def measure_detection(db, repeat: int) -> Measured:
    out = Measured("ai_detection", "Проверка на признаки AI-генерации")
    row = _sample_submission(db)
    if row is None:
        out.error = "нет работ"
        return out
    review, *_ = row
    for _ in range(repeat):
        started = time.monotonic()
        run_detection(review.id)
        out.add(time.monotonic() - started)
    return out


def measure_feedback(db, repeat: int) -> Measured:
    out = Measured("feedback_copilot", "Переписать обратную связь под тон курса")
    row = _sample_submission(db)
    if row is None:
        out.error = "нет работ"
        return out
    review, submission, _ = row
    decisions = [
        {
            "criterion": item.criterion_title,
            "score": item.final_score if item.final_score is not None else item.ai_score,
            "max_score": item.max_score,
            "action": item.reviewer_action,
            "comment": item.reviewer_comment or item.recommendation,
        }
        for item in review.items
    ]
    for _ in range(repeat):
        started = time.monotonic()
        response = AiReviewerClient().rewrite_feedback(
            text=review.draft_feedback or "Работа выполнена.",
            tone_of_voice=submission.assignment.course.tone_of_voice,
            decisions=decisions,
        )
        out.add(time.monotonic() - started)
        _remember(db, review.id, "feedback_copilot", response.metadata, out.seconds[-1])
    return out


def measure_generation(db, repeat: int) -> Measured:
    """Генерация задания с критериями — самая длинная операция и главная экономия."""

    del db
    out = Measured("task_generate", "Создать задание с критериями")
    client = task_ai.client()
    idea = {
        "idea": "Проверить, умеет ли студент спроектировать A/B-тест и обосновать размер выборки",
        "track": "Аналитика",
        "task_format": "auto",
        "total_points": 10,
    }
    for _ in range(repeat):
        started = time.monotonic()
        try:
            created = client.generate_task(idea)
            task_id = created.get("id") or created.get("task_id")
            deadline = time.monotonic() + 600
            # Готовность у конструктора называется gen_status, а не status.
            # Первый замер этого не знал и честно ждал таймаут — 600 секунд
            # вместо полутора минут. Цифра, полученная так, хуже её отсутствия.
            while time.monotonic() < deadline:
                task = client.get_task(task_id)
                state = task.get("gen_status")
                if state in ("ready", "generation_failed"):
                    if state == "generation_failed":
                        out.error = task.get("gen_error") or "генерация не удалась"
                        return out
                    break
                time.sleep(2)
            else:
                out.error = "генерация не завершилась за 10 минут"
                return out
        except Exception as error:  # noqa: BLE001
            out.error = str(error)[:120]
            return out
        out.add(time.monotonic() - started)
    return out


def measure_assist(db, repeat: int) -> list[Measured]:
    """Помощь в редакторе задания: улучшить формулировку и сочинить критерий.

    Самые частые нажатия методиста — они делаются десятками за одно задание,
    поэтому секунда разницы здесь весит больше, чем в разовой генерации."""

    del db
    field = Measured("assist_field", "Улучшить формулировку блока задания")
    criterion = Measured("assist_criterion", "Сочинить критерий с градацией")
    client = task_ai.client()
    context = {"title": "Дизайн A/B-теста", "track": "Аналитика"}
    for _ in range(repeat):
        started = time.monotonic()
        try:
            client.assist_field(
                field="statement",
                mode="improve",
                current="Спроектируйте A/B-тест для новой функции и обоснуйте размер выборки.",
                context=context,
            )
        except Exception as error:  # noqa: BLE001
            field.error = str(error)[:110]
            break
        field.add(time.monotonic() - started)

        started = time.monotonic()
        try:
            client.assist_criterion(
                max_points=3,
                title="Расчёт MDE",
                task_context=context,
                existing=["Формулирование гипотез"],
            )
        except Exception as error:  # noqa: BLE001
            criterion.error = str(error)[:110]
            break
        criterion.add(time.monotonic() - started)
    return [field, criterion]


def measure_personas(db, repeat: int) -> Measured:
    """Прогон задания на AI-персонах — проверка условия до выдачи студентам."""

    out = Measured("persona_run", "Проверить задание на AI-персонах", "прогон")
    assignment = db.scalar(select(Assignment).order_by(Assignment.created_at))
    if assignment is None:
        out.error = "нет заданий"
        return out
    for _ in range(repeat):
        run = task_ai.create_run(
            db,
            assignment,
            persona_type="student",
            idempotency_key=None,
            created_by=None,
            samples=1,
        )
        db.commit()
        started = time.monotonic()
        task_ai.execute_run(run.id)
        out.add(time.monotonic() - started)
    return out


def measure_distribution(db, repeat: int) -> list[Measured]:
    """Распределение работ — единственная автоматизация без модели вовсе.

    Очередь на время замера набирается из уже существующих работ и не
    сохраняется: сессия откатывается. Мерить распределение на пустой очереди
    бессмысленно, а заводить ради замера фиктивные работы — значит мерить не
    то, что работает в проде."""

    auto = Measured("distribution_auto", "Распределить очередь автоматически", "прогон")
    manual = Measured("distribution_manual", "Подобрать ревьюера для одной работы", "работа")

    queue = list(
        db.scalars(
            select(Submission)
            .where(Submission.status == SubmissionStatus.COMPLETED)
            .order_by(Submission.submitted_at)
        )
    )
    for submission in queue:
        submission.status = SubmissionStatus.SUBMITTED
    db.flush()
    try:
        for _ in range(repeat):
            started = time.monotonic()
            rows = proposals(db)
            auto.add(time.monotonic() - started)
            started = time.monotonic()
            reviewer_loads(db)
            manual.add(time.monotonic() - started)
    finally:
        db.rollback()

    auto.title += f" (очередь {len(rows)} работ)" if rows else " (очередь пуста)"
    return [auto, manual]


def _remember(db, review_id, stage, metadata, seconds: float) -> None:
    from app.services.review_pipeline import persist_call

    persist_call(db, review_id, stage, metadata, round(seconds * 1000))
    db.commit()


# --------------------------------------------------------------------------- #
#  Отчёт
# --------------------------------------------------------------------------- #


def persona_spend(db, limit: int) -> dict:
    """Расход прогона персон конструктор считает сам и кладёт в метрики прогона."""

    from app.models.task_ai import AiRun

    rows = [
        run.metrics
        for run in db.scalars(
            select(AiRun).where(AiRun.status == "completed").order_by(AiRun.created_at.desc()).limit(limit)
        )
        if run.metrics
    ]
    if not rows:
        return {}
    return {
        "tokens_in": round(statistics.mean(m.get("prompt_tokens", 0) for m in rows)),
        "tokens_out": round(statistics.mean(m.get("completion_tokens", 0) for m in rows)),
        "cost_usd": round(statistics.mean(m.get("cost_usd", 0.0) for m in rows), 6),
        "calls": round(statistics.mean(m.get("llm_calls", 0) for m in rows)),
    }


def spend(db, stage: str, limit: int) -> dict:
    if stage == "persona_run":
        return persona_spend(db, limit)
    rows = list(
        db.scalars(
            select(LlmCall)
            .where(LlmCall.stage == stage)
            .order_by(LlmCall.created_at.desc())
            .limit(limit)
        )
    )
    if not rows:
        return {}
    return {
        "tokens_in": round(statistics.mean(r.tokens_in for r in rows)),
        "tokens_out": round(statistics.mean(r.tokens_out for r in rows)),
        "cost_usd": round(statistics.mean(r.cost_usd for r in rows), 6),
        "calls": len(rows),
    }


def render(rows: list[dict]) -> None:
    print(f"\n{'операция':<50}{'время':>10}{'разброс':>14}{'токены':>16}{'стоимость':>12}")
    print("─" * 102)
    for row in rows:
        if row.get("error"):
            print(f"  {row['title'][:48]:<50}{'не измерено: ' + row['error']}")
            continue
        seconds = row["median_seconds"]
        # Распределение считается за миллисекунды, генерация задания — за
        # минуты. Одна единица на всю таблицу превращала бы половину строк в 0.0.
        if seconds < 1:
            pace = f"{seconds * 1000:.0f} мс"
        elif seconds < 90:
            pace = f"{seconds:.1f} с"
        else:
            pace = f"{seconds / 60:.1f} мин"
        tokens = (
            f"{row['tokens_in']}→{row['tokens_out']}" if row.get("tokens_in") is not None else "—"
        )
        money = f"${row['cost_usd']:.4f}" if row.get("cost_usd") else "—"
        print(f"  {row['title'][:48]:<50}{pace:>10}{row['spread'] or '—':>14}{tokens:>16}{money:>12}")

    print("\nЧто это заменяет\n")
    for row in rows:
        base = BASELINE_BY_OPERATION.get(row["key"])
        if not base or row.get("error"):
            continue
        human = HUMAN_AFTER_MINUTES.get(row["key"], 0.0)
        saved = saved_minutes(base.minutes, row["median_seconds"], human)
        print(
            f"  {row['title'][:46]:<48} было {base.minutes:.0f} мин → "
            f"стало {row['median_seconds'] / 60 + human:.1f} мин · экономия {saved:.1f} мин"
        )
        print(f"  {'':<48} источник: {base.source}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=2, help="сколько раз выполнить каждую операцию")
    parser.add_argument("--only", default="", help="через запятую: review, blitz, detection, feedback, generation, assist, personas, distribution")
    args = parser.parse_args()

    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    steps = {
        "review": measure_review,
        "blitz": measure_blitz,
        "detection": measure_detection,
        "feedback": measure_feedback,
        "generation": measure_generation,
        "assist": measure_assist,
        "distribution": measure_distribution,
        "personas": measure_personas,
    }

    measured: list[Measured] = []
    with SessionLocal() as db:
        for name, step in steps.items():
            if wanted and name not in wanted:
                continue
            print(f"меряю: {name}…", flush=True)
            result = step(db, args.repeat)
            measured.extend(result if isinstance(result, list) else [result])

        rows = []
        for item in measured:
            money = spend(db, item.key, args.repeat)
            rows.append(
                {
                    "key": item.key,
                    "title": item.title,
                    "unit": item.unit,
                    "runs": len(item.seconds),
                    "median_seconds": item.median,
                    "spread": item.spread,
                    "error": item.error,
                    **money,
                }
            )

    render(rows)
    REPORT.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "model": settings.ai_reviewer_model,
                "price_per_million": {
                    "in": settings.zai_input_cost_per_million,
                    "out": settings.zai_output_cost_per_million,
                },
                "operations": rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nЗамер сохранён: {REPORT.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
