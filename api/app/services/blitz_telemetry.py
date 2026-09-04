"""Сведение поведенческих событий блиц-опроса в наблюдения для ревьюера.

Три вещи, которые здесь важнее кода.

**Источник недоверенный.** События пришли из браузера студента. Их можно не
отправить, отправить не те и отправить выдуманные — консоль разработчика
открывается в два клика. Поэтому здесь нет и не может быть вывода «списал»:
модуль складывает наблюдения и помечает те, что стоит посмотреть глазами.
Отсутствие флагов не означает честности, наличие — нечестности.

**Смещения, а не время.** Клиент присылает `offset_ms` от открытия формы. Часы
на его устройстве нам не подчиняются, но длительности от их сдвига не зависят.
Единственная сверка с сервером — общая длительность против окна
`sent_at … answered_at`; она ловит грубую подделку, а не аккуратную.

**Длины, а не тексты.** У события вставки есть размер и нет содержимого:
читать буфер обмена студента мы не будем.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Отлучка короче считается обычным поведением: человек отводит взгляд, отвечает
# на сообщение, переключается на решение в соседней вкладке. Проверять
# осмысленно длинные отлучки посреди ответа, а не сам факт переключения.
LONG_AWAY_MS = 20_000

# Порог, с которого доля вставленного считается преобладающей.
PASTE_DOMINANT_SHARE = 0.5

# Текст, появившийся без единого нажатия и без вставки. Абсолютный порог нужен,
# чтобы короткий ответ не ловился на округлении батчей ввода.
PHANTOM_MIN_CHARS = 40
PHANTOM_SHARE = 0.2

# Устойчивая скорость набора. 12 знаков в секунду — это ~140 слов в минуту без
# единой паузы; на осмысленном ответе по своей работе так не печатают.
IMPLAUSIBLE_CPS = 12.0
IMPLAUSIBLE_MIN_CHARS = 80

# Допуск на сверку с сервером: сеть, задержка отправки, округление.
CLOCK_TOLERANCE_MS = 120_000

AWAY_START = ("blur", "hidden")
AWAY_END = ("focus", "visible")

FLAG_TITLES: dict[str, str] = {
    "paste_dominant": "Ответ преимущественно вставлен, а не набран",
    "phantom_insert": "Текст появился без нажатий и без вставки",
    "left_mid_answer": "Долгий уход с вкладки посреди ответа",
    "implausible_speed": "Скорость набора выше правдоподобной",
    "timeline_implausible": "Хронология клиента не сходится с серверной",
}


@dataclass
class QuestionStats:
    question_id: str
    answer_chars: int = 0
    typed_chars: int = 0
    pasted_chars: int = 0
    active_ms: int = 0
    away_ms: int = 0
    away_count: int = 0
    longest_away_ms: int = 0
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "answer_chars": self.answer_chars,
            "typed_chars": self.typed_chars,
            "pasted_chars": self.pasted_chars,
            "active_ms": self.active_ms,
            "away_ms": self.away_ms,
            "away_count": self.away_count,
            "longest_away_ms": self.longest_away_ms,
            "flags": self.flags,
        }


def _intervals(events: list, start_kinds: tuple[str, ...], end_kinds: tuple[str, ...],
               end_of_form: int, question_id: str | None = None) -> list[tuple[int, int]]:
    """Собирает пары «начало — конец» из потока событий.

    Незакрытый интервал закрывается концом формы: вкладку могли не вернуть, а
    отправить ответ с другого окна, и такой уход всё равно наблюдение.
    """

    intervals: list[tuple[int, int]] = []
    opened: int | None = None
    for event in events:
        if question_id is not None and event.question_id != question_id:
            continue
        if event.kind in start_kinds:
            # Повторное начало без конца: браузеры шлют blur и hidden подряд.
            if opened is None:
                opened = event.offset_ms
        elif event.kind in end_kinds and opened is not None:
            intervals.append((opened, max(opened, event.offset_ms)))
            opened = None
    if opened is not None:
        intervals.append((opened, max(opened, end_of_form)))
    return intervals


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Схлопывает пересечения: blur и hidden описывают один и тот же уход."""

    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def aggregate(
    *,
    events: list,
    answers: list[dict],
    sent_at: datetime | None = None,
    answered_at: datetime | None = None,
) -> dict:
    """Сводит события в статистику по вопросам и по сессии целиком."""

    ordered = sorted(events, key=lambda item: item.offset_ms)
    end_of_form = max((event.offset_ms for event in ordered), default=0)
    away = _merge(_intervals(ordered, AWAY_START, AWAY_END, end_of_form))
    answer_text = {
        str(item.get("question_id", "")): str(item.get("text") or "") for item in answers
    }

    stats: dict[str, QuestionStats] = {}
    for question_id, text in answer_text.items():
        stats[question_id] = QuestionStats(question_id=question_id, answer_chars=len(text))

    for event in ordered:
        row = stats.get(event.question_id or "")
        if row is None:
            continue
        if event.kind == "input_batch":
            row.typed_chars += max(0, event.size)
        elif event.kind in ("paste", "drop"):
            row.pasted_chars += max(0, event.size)

    for question_id, row in stats.items():
        focus = _merge(
            _intervals(ordered, ("question_focus",), ("question_blur",), end_of_form, question_id)
        )
        total = sum(end - start for start, end in focus)
        away_here = [
            _overlap(window, gap) for window in focus for gap in away
        ]
        row.away_ms = sum(away_here)
        row.away_count = sum(1 for value in away_here if value > 0)
        row.longest_away_ms = max(away_here, default=0)
        row.active_ms = max(0, total - row.away_ms)
        # Пусто — значит сбор не сработал, а не значит, что студент не набирал.
        # Считать пометки по несобранным данным — та же ошибка, что показывать
        # низкий индекс детекции при нулевом покрытии: отсутствие наблюдения
        # выдаётся за наблюдение.
        row.flags = _flags(row) if ordered else []

    total_ms = end_of_form
    session_flags: list[str] = []
    if sent_at and answered_at:
        window_ms = int((answered_at - sent_at).total_seconds() * 1000)
        if total_ms > window_ms + CLOCK_TOLERANCE_MS:
            session_flags.append("timeline_implausible")

    return {
        "questions": [row.as_dict() for row in stats.values()],
        "total_ms": total_ms,
        "away_ms": sum(end - start for start, end in away),
        "away_count": len(away),
        "event_count": len(ordered),
        "flags": session_flags,
        # Ни одного события — форму открыли в браузере без JS, отключили сбор
        # или просто ничего не прислали. Это не наблюдение «студент бездействовал».
        "collected": bool(ordered),
    }


def _flags(row: QuestionStats) -> list[str]:
    flags: list[str] = []
    if row.answer_chars and row.pasted_chars >= row.answer_chars * PASTE_DOMINANT_SHARE:
        flags.append("paste_dominant")
    unaccounted = row.answer_chars - row.typed_chars - row.pasted_chars
    if unaccounted > max(PHANTOM_MIN_CHARS, row.answer_chars * PHANTOM_SHARE):
        flags.append("phantom_insert")
    if row.longest_away_ms >= LONG_AWAY_MS:
        flags.append("left_mid_answer")
    seconds = row.active_ms / 1000
    if (
        row.typed_chars >= IMPLAUSIBLE_MIN_CHARS
        and seconds > 0
        and row.typed_chars / seconds > IMPLAUSIBLE_CPS
    ):
        flags.append("implausible_speed")
    return flags
