"""Сходится ли оценка модели с разметкой эксперта.

У каждой работы из материалов кейсодателя есть метка уровня — слабое, среднее,
хорошее. Это единственная внешняя точка отсчёта, которая у нас есть: сами баллы
эксперт не проставлял, и сравнивать «6.0 против 5.5» не с чем. Зато можно
проверить более слабое, но честное утверждение: сохраняет ли модель порядок.
Если она ставит слабой работе больше, чем хорошей, это видно без всякой шкалы.

Считаются пары работ разного уровня внутри одного задания. Пара согласованная,
если модель поставила более сильной работе строго больше; несогласованная —
если строго меньше; ничья считается отдельно и не записывается ни в чью пользу:
одинаковый балл двум разным по качеству работам — это не ошибка порядка, а
отказ различать, и смешивать эти два случая значит прятать второй.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

# Порядок уровней, заданный кейсодателем.
RANK = {"weak": 0, "medium": 1, "strong": 2}

LEVEL_NAMES = {"weak": "слабое", "medium": "среднее", "strong": "хорошее"}


@dataclass(frozen=True)
class Work:
    task: str
    level: str
    percent: float   # доля максимума, 0..100


@dataclass(frozen=True)
class Agreement:
    concordant: int = 0
    discordant: int = 0
    ties: int = 0

    @property
    def compared(self) -> int:
        return self.concordant + self.discordant + self.ties

    @property
    def share(self) -> float | None:
        """Доля согласованных пар. None — сравнивать было нечего."""

        return round(100 * self.concordant / self.compared, 1) if self.compared else None

    def __add__(self, other: "Agreement") -> "Agreement":
        return Agreement(
            self.concordant + other.concordant,
            self.discordant + other.discordant,
            self.ties + other.ties,
        )


def compare(works: list[Work]) -> Agreement:
    """Согласие по одному заданию: все пары работ разного уровня."""

    result = Agreement()
    for left, right in combinations(works, 2):
        if RANK.get(left.level) is None or RANK.get(right.level) is None:
            continue
        if RANK[left.level] == RANK[right.level]:
            continue
        stronger, weaker = (
            (left, right) if RANK[left.level] > RANK[right.level] else (right, left)
        )
        if stronger.percent > weaker.percent:
            result += Agreement(concordant=1)
        elif stronger.percent < weaker.percent:
            result += Agreement(discordant=1)
        else:
            result += Agreement(ties=1)
    return result


def by_task(works: list[Work]) -> dict[str, Agreement]:
    tasks: dict[str, list[Work]] = {}
    for work in works:
        tasks.setdefault(work.task, []).append(work)
    return {task: compare(items) for task, items in tasks.items()}


def overall(works: list[Work]) -> Agreement:
    total = Agreement()
    for agreement in by_task(works).values():
        total += agreement
    return total
