"""Что из курса — накликанное при отладке, а что живая работа методиста.

Отдельный модуль, потому что решение здесь одно и оно опасное: удалить задание
вместе с рубрикой, работами и прогонами. Правило намеренно узкое — задание
считается мусором, только если по нему **никто ничего не сдавал** и оно не из
демо-каталога. Всё, к чему приложил руку студент, неприкосновенно, даже если
называется «Тест тест 123».

Обратной стороной узости является то, что настоящее пустое задание методиста
тоже попадёт в список. Поэтому модуль ничего не удаляет сам: он возвращает
список, а решение принимает человек, увидев названия.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TaskRow:
    """Задание глазами уборки: имя, возраст и следы чужого труда."""

    id: object
    title: str
    created_at: datetime | None
    published: bool
    submissions: int
    runs: int


def is_demo(title: str, catalogue: set[str]) -> bool:
    return title.strip() in catalogue


def removable(rows: list[TaskRow], catalogue: set[str]) -> list[TaskRow]:
    """Задания, которые можно снести без потерь.

    Порядок — от старых к новым: так список читается как история отладки, а не
    как случайная выборка."""

    return sorted(
        (row for row in rows if not is_demo(row.title, catalogue) and row.submissions == 0),
        key=lambda row: (row.created_at is None, row.created_at),
    )


def kept(rows: list[TaskRow], catalogue: set[str]) -> list[TaskRow]:
    """Всё остальное — и почему оно остаётся."""

    return [row for row in rows if is_demo(row.title, catalogue) or row.submissions > 0]


def reason(row: TaskRow, catalogue: set[str]) -> str:
    if is_demo(row.title, catalogue):
        return "задание демо-курса"
    if row.submissions:
        return f"по нему сдано работ: {row.submissions}"
    return "нет работ и нет в демо-каталоге"
