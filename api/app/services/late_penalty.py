"""Штраф за нарушение срока сдачи.

Правило штрафа — часть условий задания, и методист задаёт его явно: сколько
снимать за сутки, в баллах или процентах, и есть ли потолок. Ровно поэтому оно
здесь машиночитаемое, а не вычитывается из текста условия при выставлении
оценки. Разбор свободного текста в момент грейдинга — это способ однажды тихо
поставить несправедливый балл: формулировка «штраф не применяется к работам по
уважительной причине» ничем не отличается от обычной для регулярного выражения,
а исправлять придётся оценку живого человека.

Правила нет — оценка не меняется. Это не крайний случай, а поведение по
умолчанию: большинство заданий никакого штрафа не предусматривает.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

UNITS = ("points", "percent")


@dataclass(frozen=True)
class Rule:
    """Сколько снимать за просрочку. `per_day` в баллах или процентах максимума."""

    per_day: float
    unit: str = "points"
    max_penalty: float | None = None   # потолок в тех же единицах; None — без потолка

    @property
    def is_active(self) -> bool:
        return self.per_day > 0 and self.unit in UNITS


def parse_rule(raw: dict | None) -> Rule | None:
    """Правило из `assignment.authoring.late_penalty`. Мусор — как будто его нет.

    Молча игнорировать неверное правило правильнее, чем падать при выставлении
    оценки: у ревьюера в этот момент нет ни возможности, ни полномочий чинить
    настройку задания.
    """

    if not isinstance(raw, dict):
        return None
    try:
        per_day = float(raw.get("per_day") or 0)
        top = raw.get("max_penalty")
        rule = Rule(
            per_day=per_day,
            unit=str(raw.get("unit") or "points"),
            max_penalty=float(top) if top not in (None, "") else None,
        )
    except (TypeError, ValueError):
        return None
    return rule if rule.is_active else None


def late_days(deadline_at: datetime | None, submitted_at: datetime | None) -> int:
    """Полные и начатые сутки просрочки.

    Начатые считаются целиком — это обычная академическая договорённость и
    единственная, которую можно объяснить студенту одной фразой. Опоздание на
    час и на двадцать три часа — одинаково «первые сутки».
    """

    if not deadline_at or not submitted_at or submitted_at <= deadline_at:
        return 0
    return math.ceil((submitted_at - deadline_at).total_seconds() / 86400)


def penalty(rule: Rule | None, days: int, *, score: float, max_score: float) -> float:
    """Сколько баллов снять. Никогда не больше самой оценки и не меньше нуля.

    Ниже нуля работа не опускается: штраф — это вычет из заработанного, а не
    долг. И потолок правила, и сама оценка ограничивают его сверху.
    """

    if rule is None or days <= 0 or score <= 0:
        return 0.0
    raw = rule.per_day * days
    if rule.unit == "percent":
        raw = max_score * raw / 100
    if rule.max_penalty is not None:
        cap = rule.max_penalty
        if rule.unit == "percent":
            cap = max_score * cap / 100
        raw = min(raw, cap)
    return round(min(raw, score), 2)


def describe(rule: Rule | None) -> str:
    """Правило одной строкой — как его увидят ревьюер и студент."""

    if rule is None:
        return ""
    unit = "%" if rule.unit == "percent" else " б."
    text = f"−{_num(rule.per_day)}{unit} за каждые начатые сутки просрочки"
    if rule.max_penalty is not None:
        text += f", но не больше −{_num(rule.max_penalty)}{unit}"
    return text


def explain(rule: Rule | None, days: int, amount: float) -> str:
    """Арифметика конкретной работы: за что именно сняли."""

    if not amount:
        return ""
    return f"Просрочка {days} сут. → −{_num(amount)} б. по правилу задания ({describe(rule)})"


def _num(value: float) -> str:
    return str(round(value, 2)).replace(".0", "") if value == int(value) else str(round(value, 2))
