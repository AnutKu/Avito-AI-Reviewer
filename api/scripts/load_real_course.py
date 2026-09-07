"""Наполнить кабинет настоящим курсом: реальные ДЗ, критерии и решения.

    python -m scripts.load_real_course --wipe --restore   # всё из репозитория, без модели
    python -m scripts.load_real_course --wipe --review    # заново прогнать проверку моделью
    python -m scripts.load_real_course --export           # сохранить ответы модели в git
    python -m scripts.load_real_course --report           # сравнить баллы с разметкой

Здесь живут команды, которые ходят в модель. Всё, что воспроизводится из
репозитория, вынесено в `app/real_course_loader.py` — оттуда же кабинет
поднимается на старте контейнера, без ключа и без сети.

`--review` вызывает ту же функцию, что и кабинет, когда ревьюеру назначают
работу: `review_pipeline.run_review`. Отдельного «режима демонстрации» нет —
если модель недоступна, работа останется без разбора, и это будет видно.

`--wipe` сносит всё содержимое базы. Отдельным флагом и без значения по
умолчанию: перепутать эту команду с обычным запуском не должно быть возможности.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AiSignal,
    AiStatus,
    Assignment,
    Base,
    BlitzSession,
    BlitzStatus,
    Review,
    RubricVersion,
    Snapshot,
    StatusHistory,
    Submission,
    SubmissionStatus,
)
from app.real_course import TASKS  # noqa: E402
from app.real_course_loader import (  # noqa: E402
    DATA,
    RESULTS,
    complete,
    load,
    replay,
    reschedule,
    restore,
    wipe,
)
from app.services.level_agreement import LEVEL_NAMES, Work, by_task, overall  # noqa: E402
from app.services.review_pipeline import blitz_questions_with_retries, run_review  # noqa: E402

# Сколько отказов подряд считать признаком недоступного сервиса, а не плохих работ.
MAX_FAILURES_IN_A_ROW = 3
RETRY_PAUSE_SECONDS = 10


def review_all(db) -> None:
    pending = list(
        db.scalars(
            select(Review.id)
            .join(Submission, Submission.id == Review.submission_id)
            .where(Review.ai_status.in_([AiStatus.PENDING, AiStatus.FAILED]))
            .order_by(Submission.submitted_at)
        )
    )
    print(f"К проверке работ: {len(pending)}")
    ok = failed = streak = 0
    for number, review_id in enumerate(pending, 1):
        # Подряд идущие отказы означают не плохие работы, а недоступный сервис.
        # Продолжать — значит за полминуты пометить все оставшиеся работы как
        # «ошибка проверки» и потерять понимание, какие из них вообще пробовали.
        if streak >= MAX_FAILURES_IN_A_ROW:
            left = len(pending) - number + 1
            print(
                f"\n  Прервано: {streak} отказа подряд — похоже, сервис проверки недоступен."
                f"\n  Не тронуто работ: {left}. Повторите ту же команду, когда сервис поднимется."
            )
            break
        started = time.monotonic()
        run_review(review_id)
        with SessionLocal() as fresh:
            review = fresh.get(Review, review_id)
            submission = fresh.get(Submission, review.submission_id)
            title = submission.assignment.title[:44]
            level = (
                fresh.scalar(select(Snapshot).where(Snapshot.submission_id == submission.id))
                .parsed_facts.get("expert_level")
            )
            if review.ai_status == AiStatus.READY:
                score = sum(item.ai_score or 0 for item in review.items)
                total = review.rubric_version.max_score
                ok += 1
                streak = 0
                mark = f"{score:>5.1f} / {total:<4.0f}"
            else:
                failed += 1
                streak += 1
                mark = f"  ошибка: {(review.ai_error or '')[:40]}"
        print(
            f"  [{number:>2}/{len(pending)}] {time.monotonic() - started:5.1f}с "
            f"{LEVEL_NAMES.get(level, level):<8} {mark}  {title}",
            flush=True,
        )
        if streak:
            time.sleep(RETRY_PAUSE_SECONDS)
    print(f"\nПроверено: {ok}. С ошибкой: {failed}.")


def send_blitz(db, *, limit: int) -> None:
    """Отправить дополнительные вопросы там, где разбор усомнился в понимании.

    Повод не выдуман: берутся работы, по которым модель сама выставила сигнал
    `understanding_risk` уровня medium или high, — то есть ровно те, где живой
    ревьюер и стал бы переспрашивать. Вопросы генерирует та же модель и тем же
    вызовом, что и кнопка в кабинете; заготовленных текстов здесь нет, иначе
    студенту прилетели бы вопросы про чужую работу."""

    candidates = list(
        db.execute(
            select(Review, Submission, Snapshot)
            .join(Submission, Submission.id == Review.submission_id)
            .join(Snapshot, Snapshot.submission_id == Submission.id)
            .join(AiSignal, AiSignal.review_id == Review.id)
            .where(
                Submission.status == SubmissionStatus.IN_REVIEW,
                AiSignal.kind == "understanding_risk",
                AiSignal.level.in_(["medium", "high"]),
            )
            .order_by(Submission.submitted_at)
        ).unique()
    )[:limit]

    print(f"Работ с сомнением в понимании: {len(candidates)}")
    for review, submission, snapshot in candidates:
        if db.scalar(select(BlitzSession.id).where(BlitzSession.review_id == review.id)):
            continue
        try:
            response = blitz_questions_with_retries(
                assignment=submission.assignment, snapshot=snapshot, count=3, focus=[]
            )
        except Exception as error:  # noqa: BLE001
            print(f"  вопросы не составлены: {str(error)[:70]}")
            continue
        sent = submission.submitted_at + timedelta(hours=20)
        db.add(
            BlitzSession(
                review_id=review.id,
                status=BlitzStatus.SENT,
                questions=[question.model_dump() for question in response.result.questions],
                sent_at=sent,
                due_at=sent + timedelta(hours=48),
            )
        )
        submission.status = SubmissionStatus.BLITZ_SENT
        db.add(
            StatusHistory(
                submission_id=submission.id,
                from_status=SubmissionStatus.IN_REVIEW,
                to_status=SubmissionStatus.BLITZ_SENT,
                actor_id=review.completed_by,
                comment="Отправлены дополнительные вопросы",
                created_at=sent,
            )
        )
        db.commit()
        print(f"  вопросов {len(response.result.questions)} · {submission.assignment.title[:44]}")


def export(db) -> None:
    """Сохранить ответы модели в репозиторий.

    После этого кабинет поднимается одинаково на любой машине и без ключа: там,
    где раньше был прогон на полчаса и счёт от провайдера, остаётся чтение
    файла. Записывается дословный ответ модели вместе с идентификатором
    запроса — чтобы позже можно было отличить сохранённый разбор от свежего и
    понять, откуда он взялся.
    """

    rows = db.execute(
        select(Review, Submission, Snapshot)
        .join(Submission, Submission.id == Review.submission_id)
        .join(Snapshot, Snapshot.submission_id == Submission.id)
        .where(Review.ai_status == AiStatus.READY)
        .order_by(Submission.submitted_at)
    ).all()

    reviews = []
    for review, submission, snapshot in rows:
        blitz = db.scalar(select(BlitzSession).where(BlitzSession.review_id == review.id))
        reviews.append(
            {
                "source": (snapshot.parsed_facts or {}).get("source", ""),
                "task": submission.assignment.title,
                "level": (snapshot.parsed_facts or {}).get("expert_level", ""),
                "model": review.model,
                "ai_status": review.ai_status,
                "draft_feedback": review.draft_feedback,
                "raw_result": review.raw_result,
                "items": [
                    {
                        "criterion_key": item.criterion_key,
                        "criterion_title": item.criterion_title,
                        "max_score": item.max_score,
                        "ai_score": item.ai_score,
                        "verdict": item.verdict,
                        "confidence": item.confidence,
                        "evidence": item.evidence,
                        "recommendation": item.recommendation,
                    }
                    for item in review.items
                ],
                "signals": [
                    {
                        "kind": signal.kind,
                        "level": signal.level,
                        "summary": signal.summary,
                        "grounds": signal.grounds,
                        "limitations": signal.limitations,
                    }
                    for signal in review.signals
                ],
                "blitz": {"questions": blitz.questions} if blitz else None,
            }
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "note": (
            "Дословные ответы модели на работы реального курса. Снято прогоном "
            "scripts/load_real_course.py --review; воспроизводится ключом --restore."
        ),
        "reviews": reviews,
    }
    RESULTS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8"
    )
    size = RESULTS.stat().st_size / 1024
    with_blitz = sum(1 for row in reviews if row["blitz"])
    print(
        f"Сохранено разборов: {len(reviews)} (из них с вопросами: {with_blitz}) "
        f"в {RESULTS.relative_to(ROOT.parent)}, {size:.0f} КБ."
    )


def report(db) -> None:
    """Сравнить баллы модели с разметкой кейсодателя."""

    rows = db.execute(
        select(Assignment.title, Snapshot.parsed_facts, RubricVersion.max_score, Review.id)
        .join(Submission, Submission.assignment_id == Assignment.id)
        .join(Snapshot, Snapshot.submission_id == Submission.id)
        .join(Review, Review.submission_id == Submission.id)
        .join(RubricVersion, RubricVersion.id == Review.rubric_version_id)
        .where(Review.ai_status == AiStatus.READY)
    ).all()

    works: list[Work] = []
    # У одного задания может быть два решения одного уровня. В таблице
    # показывается среднее, в подсчёте пар каждое участвует отдельно.
    scores: dict[tuple[str, str], list[float]] = {}
    for title, facts, max_score, review_id in rows:
        review = db.get(Review, review_id)
        if not review.items or not max_score:
            continue
        percent = 100 * sum(item.ai_score or 0 for item in review.items) / max_score
        level = (facts or {}).get("expert_level", "")
        works.append(Work(task=title, level=level, percent=percent))
        scores.setdefault((title, level), []).append(percent)

    print("\nОценка модели против разметки кейсодателя\n")
    print(f"  {'задание':<44}{'слабое':>9}{'среднее':>9}{'хорошее':>9}   порядок")
    for title, agreement in sorted(by_task(works).items()):
        cells = "".join(
            f"{sum(scores[(title, level)]) / len(scores[(title, level)]):>8.0f}%"
            if (title, level) in scores
            else f"{'—':>9}"
            for level in ("weak", "medium", "strong")
        )
        verdict = "—" if agreement.share is None else f"{agreement.share:.0f}%"
        print(f"  {title[:43]:<44}{cells}   {verdict}")

    total = overall(works)
    print(
        f"\n  Пар сравнено: {total.compared}. Порядок сохранён: {total.concordant}, "
        f"нарушен: {total.discordant}, одинаковый балл: {total.ties}."
    )
    if total.share is not None:
        print(f"  Доля согласованных пар: {total.share}%.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true", help="снести всё содержимое базы")
    parser.add_argument(
        "--restore", action="store_true", help="собрать кабинет из репозитория, без обращения к модели"
    )
    parser.add_argument("--review", action="store_true", help="прогнать AI-проверку после загрузки")
    parser.add_argument("--review-only", action="store_true", help="только догнать непроверенное")
    parser.add_argument("--rerun", metavar="SLUG", help="сбросить разбор задания и проверить заново")
    parser.add_argument("--export", action="store_true", help="сохранить ответы модели в репозиторий")
    parser.add_argument("--report", action="store_true", help="сравнить баллы с разметкой")
    parser.add_argument(
        "--reschedule", action="store_true", help="пересчитать даты курса от сегодняшнего дня"
    )
    parser.add_argument(
        "--blitz", nargs="?", type=int, const=4, metavar="N",
        help="отправить дополнительные вопросы по N работам с сомнением в понимании",
    )
    parser.add_argument(
        "--complete", nargs="?", type=int, const=3, metavar="KEEP_OPEN",
        help="закрыть проверку, оставив в работе последние KEEP_OPEN заданий (по умолчанию 3)",
    )
    args = parser.parse_args()

    if not DATA.exists():
        print("Нет текстов ДЗ. Сначала: python -m scripts.extract_homework")
        return 1

    standalone = (
        args.restore or args.review_only or args.report or args.export
        or args.reschedule or args.complete is not None or args.blitz is not None
    )

    with SessionLocal() as db:
        if args.wipe:
            Base.metadata.create_all(bind=engine)
            wipe(db)
            print("База очищена.")
        if args.restore:
            summary = restore(db)
            print(
                f"Восстановлено из репозитория: работ {summary['works']}, "
                f"разборов {summary['reviews']}, закрыто {summary['closed']} "
                f"(принято {summary['accepted']}, изменено {summary['changed']})."
            )
        elif not standalone:
            loaded = load(db, now=datetime.now(UTC))
            print(f"Загружено: заданий {len(TASKS)}, новых работ {loaded['created']}.")
            for title in loaded["refreshed"]:
                print(f"  условие обновлено из файла: {title}")
        if args.rerun:
            task = next((item for item in TASKS if item.slug == args.rerun), None)
            if task is None:
                print(f"Нет такого задания: {args.rerun}")
                return 1
            count = 0
            for review in db.scalars(
                select(Review)
                .join(Submission, Submission.id == Review.submission_id)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .where(Assignment.title == task.title)
            ):
                review.ai_status = AiStatus.PENDING
                count += 1
            db.commit()
            print(f"Сброшено разборов: {count} по заданию «{task.title}».")
        if args.review or args.review_only or args.rerun:
            review_all(db)
        if args.blitz is not None:
            send_blitz(db, limit=args.blitz)
        if args.complete is not None:
            summary = complete(db, keep_open=args.complete)
            share = (
                round(100 * summary["accepted"] / (summary["accepted"] + summary["changed"]), 1)
                if summary["accepted"] + summary["changed"]
                else None
            )
            print(
                f"Закрыто работ: {summary['closed']}. Решений по критериям: "
                f"принято {summary['accepted']}, изменено {summary['changed']}"
                + (f" (согласие {share}%)." if share is not None else ".")
            )
        if args.reschedule:
            moved = reschedule(db, now=datetime.now(UTC))
            print(f"Даты пересчитаны от {datetime.now(UTC):%d.%m.%Y}: работ {moved}.")
        if args.export:
            export(db)
        if args.report or args.review or args.review_only or args.complete is not None:
            report(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
