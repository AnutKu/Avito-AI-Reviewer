"""Решения ревьюера для демонстрационных данных — выведенные, а не выдуманные.

Настоящих решений по работам из материалов кейсодателя не существует: он передал
работы и метки уровня («слабое», «среднее», «хорошее»), но не проставленные
баллы. Чтобы в кабинете появилась статистика — успеваемость, доля согласия
ревьюера с моделью, критерии с частыми правками, — решения приходится
достроить. Вопрос только в том, из чего.

Случайные правки дали бы ровный шум по всем критериям: любая аналитика по ним
показывала бы одно и то же и ничего не значила. Здесь вместо этого берётся
единственная внешняя точка отсчёта, которая есть, — метка уровня. Ревьюер
соглашается с моделью, пока её оценка попадает в диапазон, ожидаемый для работы
такого уровня, и правит там, где расходится. Правки при этом ложатся туда, где
модель и сама менее уверена.

Получается не «как было на самом деле» (этого мы не знаем), а «как выглядела бы
проверка, если бы ревьюер держался разметки эксперта». Данные, размеченные этим
модулем, помечаются в `raw_result` — чтобы их нельзя было принять за решения
живого человека.
"""

from __future__ import annotations

from dataclasses import dataclass

# Куда ревьюер тянет итог для работы каждого уровня — доля максимума.
# Границы взяты из самих критериев: «зачёт» в условиях стоит около 60%, слабая
# работа его не берёт, хорошая берёт с запасом.
TARGET_PERCENT = {"weak": 35.0, "medium": 62.0, "strong": 88.0}

# Насколько ревьюер готов не спорить. Пятнадцать процентных пунктов — это
# примерно один критерий из шести: расхождение в один критерий не повод
# переписывать чужую работу.
TOLERANCE = 15.0

# Баллы в рубриках кратны половине — мельче ревьюер не ставит.
STEP = 0.5

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

LOWERED = "Балл снижен: подтверждения в работе недостаточно для такой оценки."
RAISED = "Балл повышен: требование выполнено, разбор это упустил."


@dataclass(frozen=True)
class Judgement:
    """Вывод модели по одному критерию."""

    key: str
    ai_score: float
    max_score: float
    confidence: str = "medium"


@dataclass(frozen=True)
class Decision:
    key: str
    action: str          # accepted | changed | rejected
    final_score: float
    comment: str = ""


def _rounded(value: float) -> float:
    return round(value * 2) / 2


def _order(items: list[Judgement], *, raising: bool) -> list[Judgement]:
    """Кого ревьюер оспорит первым.

    Сначала то, в чём модель и сама менее уверена: спорить с выводом, который
    она пометила как надёжный, — более сильное утверждение, и приберечь его
    правильнее на случай, когда без этого не обойтись."""

    def room(item: Judgement) -> float:
        return item.max_score - item.ai_score if raising else item.ai_score

    return sorted(
        items,
        key=lambda item: (CONFIDENCE_ORDER.get(item.confidence, 1), -room(item), item.key),
    )


def calibrate(
    items: list[Judgement],
    *,
    level: str,
    tolerance: float = TOLERANCE,
) -> list[Decision]:
    """Решения ревьюера по всем критериям работы известного уровня.

    Уровень неизвестен или шкала пустая — ревьюер соглашается со всем: без точки
    отсчёта у него нет оснований спорить."""

    if not items:
        return []
    maximum = sum(item.max_score for item in items)
    target = TARGET_PERCENT.get(level)
    total = sum(item.ai_score for item in items)
    if maximum <= 0 or target is None:
        return [Decision(item.key, "accepted", item.ai_score) for item in items]

    if abs(100 * total / maximum - target) <= tolerance:
        return [Decision(item.key, "accepted", item.ai_score) for item in items]

    need = _rounded(maximum * target / 100 - total)
    raising = need > 0
    final = {item.key: item.ai_score for item in items}
    order = _order(items, raising=raising)
    # Два прохода. В первом ревьюер двигает каждый критерий не больше чем на
    # половину его веса: расхождение в целую работу — это расхождение по многим
    # пунктам, а не один обнулённый критерий. Второй проход добирает остаток,
    # если после первого итог всё ещё не сходится.
    for limit in (0.5, 1.0):
        for item in order:
            if abs(need) < STEP:
                break
            ceiling = item.max_score * limit
            moved = abs(item.ai_score - final[item.key])
            room = item.max_score - final[item.key] if raising else final[item.key]
            move = _rounded(min(room, abs(need), max(ceiling - moved, 0)))
            if move < STEP:
                continue
            final[item.key] = round(final[item.key] + (move if raising else -move), 2)
            need = round(need - (move if raising else -move), 2)

    # Отклонения вывода («rejected») здесь не появляется, и это осознанно. По
    # одним баллам не отличить «модель завысила оценку» от «модель сослалась на
    # то, чего в работе нет», — а отклонение означает именно второе. Проставить
    # его по догадке значит испортить ровно ту статистику, ради которой всё это
    # и считается: «критерии, с выводами по которым ревьюер не согласился».
    return [
        Decision(item.key, "accepted", final[item.key])
        if final[item.key] == item.ai_score
        else Decision(
            item.key, "changed", final[item.key], RAISED if raising else LOWERED
        )
        for item in items
    ]


def agreed(decisions: list[Decision]) -> int:
    return sum(1 for decision in decisions if decision.action == "accepted")
