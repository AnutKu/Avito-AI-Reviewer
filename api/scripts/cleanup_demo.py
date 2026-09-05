"""Убрать задания, накликанные при отладке.

    python -m scripts.cleanup_demo          # только показать
    python -m scripts.cleanup_demo --yes    # удалить показанное

Внутри контейнера:

    docker compose exec api python -m scripts.cleanup_demo

Удаление каскадное: вместе с заданием уходят его рубрики, AI-прогоны и
рекомендации. Поэтому по умолчанию скрипт ничего не трогает и печатает список —
последнее слово за человеком, который узнаёт свои названия.
"""

from __future__ import annotations

import sys

from sqlalchemy import func, select

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import Assignment, Submission  # noqa: E402
from app.models.task_ai import AiRun  # noqa: E402
from app.seed import HISTORY_ASSIGNMENTS, LIVE_ASSIGNMENTS  # noqa: E402
from app.services.demo_cleanup import TaskRow, reason, removable  # noqa: E402

CATALOGUE = {spec["title"] for spec in (*HISTORY_ASSIGNMENTS, *LIVE_ASSIGNMENTS)}


def collect(db) -> list[TaskRow]:
    works = dict(
        db.execute(
            select(Submission.assignment_id, func.count()).group_by(Submission.assignment_id)
        ).all()
    )
    runs = dict(
        db.execute(select(AiRun.assignment_id, func.count()).group_by(AiRun.assignment_id)).all()
    )
    return [
        TaskRow(
            id=assignment.id,
            title=assignment.title,
            created_at=assignment.created_at,
            published=assignment.published_at is not None,
            submissions=works.get(assignment.id, 0),
            runs=runs.get(assignment.id, 0),
        )
        for assignment in db.scalars(select(Assignment).order_by(Assignment.created_at))
    ]


def main() -> int:
    apply = "--yes" in sys.argv
    with SessionLocal() as db:
        rows = collect(db)
        junk = removable(rows, CATALOGUE)

        print(f"Всего заданий: {len(rows)}. Под уборку подходит: {len(junk)}.\n")
        if not junk:
            print("Ничего лишнего не нашлось.")
            return 0

        for row in junk:
            when = row.created_at.strftime("%d.%m.%Y") if row.created_at else "дата неизвестна"
            state = "опубликовано" if row.published else "черновик"
            runs = f", прогонов AI: {row.runs}" if row.runs else ""
            print(f"  • «{row.title}» — {when}, {state}, работ нет{runs}")

        if not apply:
            print("\nЭто предпросмотр, ничего не удалено. Повторите с --yes, если список верный.")
            print("\nОстаётся на месте:")
            for row in rows:
                if row not in junk:
                    print(f"  • «{row.title}» — {reason(row, CATALOGUE)}")
            return 0

        for row in junk:
            db.delete(db.get(Assignment, row.id))
        db.commit()
        print(f"\nУдалено заданий: {len(junk)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
