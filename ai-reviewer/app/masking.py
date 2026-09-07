"""Обратимое маскирование данных перед отправкой в Z.AI.

Провайдер не должен видеть ни персональных данных студента, ни секретов,
которые он закоммитил в репозиторий. При этом ревьюер обязан видеть настоящие
цитаты из работы: на них держится вся проверяемость разбора. Поэтому здесь
именно ОБРАТИМОЕ маскирование, а не вычёркивание.

    решение → [PERSON_1] уходит в модель → ответ с [PERSON_1] → «Петров» на экране

Наружу уходит плейсхолдер, обратно приходит подстановка. Модель при этом
продолжает рассуждать связно: одна и та же сущность в пределах запроса всегда
получает один и тот же плейсхолдер, так что «тот же человек» и «тот же ключ»
для неё остаются тем же самым.

**Слой отказывает закрыто.** Если маскирование включено, а модель не
загрузилась — запрос завершается ошибкой, а не уходит к провайдеру как есть.
Молча отправить неотмаскированное значит ровно то, ради чего слой и заводился.

Что НЕ маскируется, и это решение, а не недоделка:

* системный промпт — в нём JSON Schema, справочник признаков и инструкции.
  NER там найдёт «организации» в названиях полей и порежет схему;
* условие задания и критерии рубрики — их пишет методист, это учебный материал,
  а не персональные данные студента. Замаскированное условие сделало бы задачу
  непонятной модели, а ключи критериев обязаны совпадать дословно.

Маскируется то, что пришло от человека и про человека: снапшот решения, ответы
студента на блиц, черновик обратной связи.
"""

from __future__ import annotations

import re
import sys
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import settings


class MaskingUnavailable(RuntimeError):
    """Маскирование включено, но не работает. Отправлять сырое нельзя."""


# Плейсхолдер намеренно не похож на [REDACTED:LABEL] из predict.py: ту форму
# детерминированный слой считает инертной и не трогает, а нам нужна своя.
# Двойные скобки, а не кавычки-ёлочки: «…» в русском тексте встречаются на
# каждом шагу — «ПАО «Сбербанк»» столкнулось бы с разделителем плейсхолдера.
# Форма ASCII и дешёвая по токенам; последовательность [[СЛОВО_ЧИСЛО]] в коде и
# прозе не встречается.
_PLACEHOLDER = "[[{label}_{number}]]"
_PLACEHOLDER_RE = re.compile(r"\[\[([A-Z_]+)_(\d+)\]\]")


@dataclass(frozen=True)
class Masked:
    """Текст для провайдера и способ вернуть исходные значения."""

    text: str
    # Исходник после NFC — ровно та строка, из которой вырезаны спаны. Проверка
    # цитат обязана идти по ней, а не по тому, что пришло на вход: смещения
    # детектора считаются по нормализованному тексту, и на составных символах
    # (диакритика, вставки из PDF) длина после NFC меняется.
    source: str
    # плейсхолдер → исходное значение
    mapping: dict[str, str]

    @property
    def hits(self) -> int:
        return len(self.mapping)

    def restore(self, text: str) -> str:
        """Обратная подстановка в ответе модели.

        Плейсхолдеры заменяются от длинных к коротким: «PERSON_1» — префикс
        «PERSON_10», и замена в обратном порядке съела бы номер.
        """

        if not self.mapping:
            return text
        for placeholder in sorted(self.mapping, key=len, reverse=True):
            text = text.replace(placeholder, self.mapping[placeholder])
        return text


class _NullMasker:
    """Маскирование выключено конфигом. Ничего не меняет и об этом не врёт."""

    enabled = False

    def mask(self, text: str) -> Masked:
        # NFC всё равно применяем: иначе проверка цитат идёт по одной строке при
        # включённом слое и по другой при выключенном.
        normalized = unicodedata.normalize("NFC", text)
        return Masked(text=normalized, source=normalized, mapping={})


class _ModelMasker:
    """Обёртка над Detector из бандла модели.

    Detector грузится лениво и один раз на процесс: веса — 700 МБ, и держать их
    в памяти воркера, который сегодня не разбирал ни одной работы, незачем.
    Загрузка под замком — иначе два одновременных запроса поднимут две копии.
    """

    enabled = True

    def __init__(
        self,
        bundle: Path,
        device: str,
        labels: frozenset[str],
        min_score: float = 0.0,
        min_length: int = 1,
    ):
        self._bundle = bundle
        self._device = device
        self._labels = labels
        self._min_score = min_score
        self._min_length = min_length
        self._detector = None
        self._lock = threading.Lock()

    def _keep(self, span, original: str) -> bool:
        """Стоит ли маскировать этот спан.

        Спан детерминированного слоя проходит всегда: score у него None, потому
        что у регулярки нет вероятности, и подставлять туда единицу было бы
        враньём — а резать порогом нечего.

        Отсев касается только NER: на коде она заражается контекстом и после
        настоящей строки с паролем продолжает метить PASSWORD на соседних. Эти
        спаны приходят с низкой уверенностью и часто рвут слово посередине.
        """

        if span.label not in self._labels:
            return False
        if span.source != "ner":
            return True
        if len(original.strip()) < self._min_length:
            return False
        return span.score is None or span.score >= self._min_score

    def _load(self):
        if self._detector is not None:
            return self._detector
        with self._lock:
            if self._detector is not None:
                return self._detector
            if not (self._bundle / "config.json").exists():
                raise MaskingUnavailable(
                    f"Бандл модели маскирования не найден: {self._bundle}. "
                    "Смонтируйте его в контейнер или выключите MASKING_ENABLED."
                )
            # Бандл кладёт рядом свой core/ и рассчитывает найти его в sys.path —
            # ровно так же, как это делает predict.py при запуске из каталога.
            if str(self._bundle) not in sys.path:
                sys.path.insert(0, str(self._bundle))
            try:
                from predict import Detector
            except ImportError as exc:
                raise MaskingUnavailable(
                    f"Не удалось импортировать predict.Detector из {self._bundle}: {exc}"
                ) from exc
            try:
                self._detector = Detector(str(self._bundle), device=self._device)
            except Exception as exc:
                raise MaskingUnavailable(f"Модель маскирования не загрузилась: {exc}") from exc
            return self._detector

    def mask(self, text: str) -> Masked:
        normalized = unicodedata.normalize("NFC", text or "")
        if not normalized.strip():
            return Masked(text=normalized, source=normalized, mapping={})
        detector = self._load()
        # Detector считает смещения по NFC-нормализованному тексту и сам его
        # нормализует. Режем ту же строку, что видел он, иначе на составных
        # символах спаны «поедут» и вырежется не то.
        try:
            spans = detector.spans(normalized)
        except Exception as exc:
            raise MaskingUnavailable(f"Маскирование не отработало: {exc}") from exc

        mapping: dict[str, str] = {}
        by_value: dict[tuple[str, str], str] = {}
        # Счётчик свой на каждую метку: сквозная нумерация давала PERSON_1 рядом
        # с LOGIN_2, и это читается как последовательность, а не как «первый
        # человек, первый логин».
        counters: dict[str, int] = {}
        parts: list[str] = []
        cursor = 0
        for span in spans:
            original = normalized[span.start:span.end]
            if not self._keep(span, original):
                continue
            key = (span.label, original)
            placeholder = by_value.get(key)
            if placeholder is None:
                # Один и тот же человек — один и тот же плейсхолдер в пределах
                # запроса: иначе модель видит трёх разных людей там, где один,
                # и рассуждает о работе неверно.
                counters[span.label] = counters.get(span.label, 0) + 1
                placeholder = _PLACEHOLDER.format(label=span.label, number=counters[span.label])
                by_value[key] = placeholder
                mapping[placeholder] = original
            parts.append(normalized[cursor:span.start])
            parts.append(placeholder)
            cursor = span.end
        parts.append(normalized[cursor:])
        return Masked(text="".join(parts), source=normalized, mapping=mapping)


_masker: _NullMasker | _ModelMasker | None = None


def masker() -> _NullMasker | _ModelMasker:
    """Один экземпляр на процесс. Веса грузятся не здесь, а при первом тексте."""

    global _masker
    if _masker is None:
        if not settings.masking_enabled:
            _masker = _NullMasker()
        else:
            _masker = _ModelMasker(
                bundle=Path(settings.masking_model_path),
                device=settings.masking_device,
                labels=frozenset(settings.masking_labels),
                min_score=settings.masking_min_score,
                min_length=settings.masking_min_length,
            )
    return _masker


def mask(text: str) -> Masked:
    """Замаскировать текст перед отправкой провайдеру."""

    return masker().mask(text)


def restore_all(text: str, *parts: Masked) -> str:
    """Обратная подстановка по нескольким маскировкам сразу.

    В одном запросе маскируется больше одного текста — например, вопросы и
    ответы блица, — а ответ модели приходит один.
    """

    for part in parts:
        text = part.restore(text)
    return text


def leftovers(text: str) -> list[str]:
    """Плейсхолдеры, которые остались в тексте после подстановки.

    Модель может исказить плейсхолдер, и тогда он доедет до экрана как есть.
    Это не ошибка данных — утечки здесь нет, — но признак того, что часть
    цитаты не восстановилась, и проверка цитат её отбросит.
    """

    return sorted({match.group(0) for match in _PLACEHOLDER_RE.finditer(text)})


def status() -> dict:
    """Что сказать о слое в /health. Веса при этом не грузятся."""

    if not settings.masking_enabled:
        return {"enabled": False}
    bundle = Path(settings.masking_model_path)
    return {
        "enabled": True,
        "device": settings.masking_device,
        "bundle": str(bundle),
        "bundle_present": (bundle / "config.json").exists(),
        "labels": sorted(settings.masking_labels),
    }


# Тип для аннотаций вызывающего кода: маскировщик — это то, что умеет mask().
Masker = Callable[[str], Masked]
