"""Шкала индекса признаков ИИ. Число считает этот модуль, а не модель.

Три свойства, ради которых расчёт вынесен из LLM:

* **воспроизводимость** — у модели нет внутренней шкалы, на которой 73 и 68
  отличались бы; между прогонами она даёт разные числа на том же тексте;
* **разложимость** — индекс возвращается вместе со слагаемыми, и ревьюер видит,
  из чего он собрался, а не одно число;
* **асимметрия** — знак вклада есть свойство признака, а не ответа модели.
  Разрывы `execution_count`, упавшие ячейки, следы отладки — свидетельство
  В ПОЛЬЗУ самостоятельности, поэтому входят со знаком минус. Их отсутствие не
  значит ничего: «Restart & Run All» перед коммитом стирает историю у кого угодно.
  Проверено на размеченных фикстурах курса: при сложении «чистая история =
  признак ИИ» хорошее решение набирало 55 из 100, а слабое проходило как чистое.

Модуль чистый: ни БД, ни сети, ни настроек кроме словаря переопределений весов.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings

# Отметка «мы ничего не наблюдали». Не «30% вероятности»: следы работы человека
# уводят индекс ниже, следы генерации — выше.
BASE_SCORE = 30.0

# Кто считает величину признака.
FACTS = "facts"  # непрерывная формула из parsed_facts, ответ модели игнорируется
TEXT = "text"  # число подтверждённых цитат модели

# Ниже этого числа code-ячеек факты по ноутбуку статистикой не являются:
# на двух ячейках «порядок выполнения» не наблюдение, а совпадение.
MIN_CODE_CELLS = 5

# Объём, начиная с которого считаем, что смотреть было на что.
FULL_VOLUME_CHARS = 8_000

CATEGORY_NO_SIGNS = "no_signs"
CATEGORY_TOOL_ASSISTED = "tool_assisted"
CATEGORY_LIKELY_GENERATED = "likely_generated"

# Вердикт голосования моделей → категория кабинета. Слова разные, деление одно:
# сервису ai-reviewer три категории названы так, как о них думает человек,
# кабинет хранит те же три под своими давними именами, и переименовывать
# половину схемы ради совпадения строк смысла нет.
VERDICT_CATEGORY: dict[str, str] = {
    "human": CATEGORY_NO_SIGNS,
    "human_ai_assisted": CATEGORY_TOOL_ASSISTED,
    "ai": CATEGORY_LIKELY_GENERATED,
}

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


@dataclass(frozen=True)
class IndicatorSpec:
    key: str
    direction: int  # +1 повышает индекс, −1 понижает
    weight: float
    source: str
    title: str


# Σ повышающих = 86, Σ понижающих = 56. Суммы намеренно разные: свидетельств
# генерации мы умеем перечислить больше, чем свидетельств ручной работы.
INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec("task_mismatch", +1, 18, TEXT, "Решает не ту задачу или опирается на чужие данные"),
    IndicatorSpec("internal_contradiction", +1, 16, TEXT, "Текст противоречит коду или выводу ячейки"),
    IndicatorSpec("unused_scaffolding", +1, 14, TEXT, "Импорты и функции, которые нигде не применены"),
    IndicatorSpec("explains_the_obvious", +1, 10, TEXT, "Комментарии объясняют тривиальное"),
    IndicatorSpec("tutorial_shape", +1, 8, TEXT, "Структура учебного примера, а не решения задачи"),
    IndicatorSpec("verbose_uniform_markdown", +1, 8, TEXT, "Обильные однородные объяснения"),
    IndicatorSpec("generic_naming", +1, 6, TEXT, "Безликие имена без привязки к предметной области"),
    IndicatorSpec("style_uniformity", +1, 6, TEXT, "Однородный стиль на большом объёме"),
    IndicatorSpec("execution_disorder", -1, 14, FACTS, "Разрывы и непорядок в execution_count"),
    IndicatorSpec("debug_leftovers", -1, 12, TEXT, "Следы отладки и закомментированный код"),
    IndicatorSpec("failed_cells", -1, 10, FACTS, "Упавшие ячейки в истории выполнения"),
    IndicatorSpec("domain_naming", -1, 8, TEXT, "Доменные имена и личные пометки"),
    IndicatorSpec("unrun_cells", -1, 6, FACTS, "Ячейки, которые не запускались"),
    IndicatorSpec("text_inconsistency", -1, 6, TEXT, "Опечатки и непоследовательность изложения"),
)

BY_KEY: dict[str, IndicatorSpec] = {spec.key: spec for spec in INDICATORS}
TEXT_KEYS: tuple[str, ...] = tuple(spec.key for spec in INDICATORS if spec.source == TEXT)
FACTS_KEYS: tuple[str, ...] = tuple(spec.key for spec in INDICATORS if spec.source == FACTS)


@dataclass(frozen=True)
class Contribution:
    key: str
    title: str
    direction: int
    weight: float
    magnitude: float
    points: float
    evidence: list[dict] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "direction": self.direction,
            "weight": self.weight,
            "magnitude": round(self.magnitude, 3),
            "points": round(self.points, 2),
            "evidence": self.evidence,
            "note": self.note,
        }


@dataclass(frozen=True)
class DetectionScore:
    score: int
    coverage: float
    confidence: str
    category: str | None
    contributions: list[Contribution]

    @property
    def is_reportable(self) -> bool:
        """Показывать ли число вообще. Низкое покрытие — не низкий индекс."""

        return self.confidence != CONFIDENCE_LOW


def weight_of(spec: IndicatorSpec) -> float:
    """Вес с учётом переопределения из конфига — иначе якорный тест нечем двигать."""

    return float(settings.detection_weights.get(spec.key, spec.weight))


def _ratio(value: float, ceiling: float) -> float:
    if ceiling <= 0:
        return 0.0
    return min(max(value, 0.0) / ceiling, 1.0)


def normalize(text: str) -> str:
    """Схлопывает пробелы: модель переносит цитату иначе, чем она лежит в файле."""

    return " ".join(text.split())


def _execution_disorder(counts: list[int]) -> float:
    """Максимум из двух свидетельств живой сессии: непорядок и перезапуск ядра."""

    ordered = [count for count in counts if isinstance(count, int)]
    disorder = 0.0
    if len(ordered) > 1:
        drops = sum(1 for a, b in zip(ordered, ordered[1:]) if b < a)
        disorder = _ratio(drops / (len(ordered) - 1), 0.15)
    restart = 0.0
    if ordered:
        smallest = min(ordered)
        restart = 1.0 if smallest > 3 else 0.5 if smallest > 1 else 0.0
    return max(disorder, restart)


def observable_notebooks(parsed_facts: dict) -> list[dict]:
    return [
        notebook
        for notebook in parsed_facts.get("notebooks", []) or []
        if notebook.get("code_cells", 0) >= MIN_CODE_CELLS
    ]


def facts_magnitudes(parsed_facts: dict) -> dict[str, float]:
    """Величины признаков процесса.

    По репозиторию берётся максимум, а не среднее: признаки оправдательные, и один
    ноутбук с живой историей — уже свидетельство ручной работы, даже если рядом
    лежит второй, прогнанный начисто.
    """

    notebooks = observable_notebooks(parsed_facts)
    if not notebooks:
        return {}
    magnitudes = {key: 0.0 for key in FACTS_KEYS}
    for notebook in notebooks:
        cells = max(notebook.get("code_cells", 0), 1)
        magnitudes["execution_disorder"] = max(
            magnitudes["execution_disorder"],
            _execution_disorder(notebook.get("execution_counts", [])),
        )
        magnitudes["unrun_cells"] = max(
            magnitudes["unrun_cells"],
            _ratio(notebook.get("unrun_cells", 0) / cells, 0.20),
        )
        magnitudes["failed_cells"] = max(
            magnitudes["failed_cells"],
            _ratio(notebook.get("failed_cells", 0) / cells, 0.10),
        )
    return magnitudes


def text_magnitude(evidence: list[dict], snapshot: str) -> float:
    """Величина = число мест, подтверждённых снапшотом, но не больше трёх.

    Силу признака у модели не спрашиваем: на трёхбалльной самооценке LLM
    кучкуется в «medium», и это число ничем не обосновано. Перечислить места
    она может, а места мы проверяем.
    """

    haystack = normalize(snapshot)
    verified = [
        item
        for item in evidence
        if item.get("quote") and normalize(item["quote"]) in haystack
    ]
    return min(len(verified), 3) / 3


def coverage(parsed_facts: dict) -> float:
    """Сколько всего было наблюдать — не сколько признаков сработало.

    Половина веса у признаков процесса (есть ли вообще ноутбук с историей),
    половина у объёма. Обрезанный снапшот штрафуется отдельно: работа, у которой
    часть файлов не доехала до модели, не может давать уверенный вывод об авторстве.
    """

    facts_share = 1.0 if observable_notebooks(parsed_facts) else 0.0
    volume = _ratio(parsed_facts.get("snapshot_chars", 0), FULL_VOLUME_CHARS)
    penalty = 0.2 if parsed_facts.get("truncated") else 0.0
    return max(0.0, 0.55 * facts_share + 0.45 * volume - penalty)


def confidence_of(value: float, parsed_facts: dict) -> str:
    if value >= 0.7 and not parsed_facts.get("truncated"):
        return CONFIDENCE_HIGH
    if value >= 0.4:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def category_of(score: int, confidence: str, verdict: str | None = None) -> str | None:
    """Категорию называет голосование прогонов, если оно состоялось.

    С этого момента число и категория отвечают на разные вопросы: индекс — «что
    наблюдается и с каким весом», вердикт — «чем это, по мнению большинства
    прогонов, является». Разойтись им позволено: расхождение видно ревьюеру
    рядом с раскладкой и само по себе повод посмотреть работу внимательнее.
    Пороги по индексу — запасной путь: старые прогоны и вызовы без голосования
    делятся ровно как раньше.

    При низком покрытии категория не выставляется независимо от вердикта:
    наблюдать было нечего, и голосование трёх прогонов по пустому месту сходится
    не лучше, чем один.
    """

    if confidence == CONFIDENCE_LOW:
        return None
    if verdict in VERDICT_CATEGORY:
        return VERDICT_CATEGORY[verdict]
    if score < 35:
        return CATEGORY_NO_SIGNS
    if score <= 70:
        return CATEGORY_TOOL_ASSISTED
    return CATEGORY_LIKELY_GENERATED


def compute(
    *,
    parsed_facts: dict,
    snapshot_content: str,
    indicators: list[dict],
    verdict: str | None = None,
) -> DetectionScore:
    """`indicators` — то, что вернула модель: [{key, evidence, note}].

    Признаки с источником FACTS из ответа модели игнорируются целиком: их
    величину даёт `parsed_facts`, а модель может лишь приложить комментарий.

    `verdict` — победивший вердикт голосования прогонов, если оно было. Число
    от него не зависит ни при каком значении: индекс остаётся тем же самым
    детерминированным сложением, и воспроизводимость, ради которой он вынесен
    из LLM, никуда не девается. Вердикт решает только деление на категории.
    """

    notes = {
        item.get("key"): item.get("note", "")
        for item in indicators
        if item.get("key") in BY_KEY
    }
    evidence_by_key = {
        item["key"]: item.get("evidence", []) or []
        for item in indicators
        if item.get("key") in BY_KEY and BY_KEY[item["key"]].source == TEXT
    }

    magnitudes = dict(facts_magnitudes(parsed_facts))
    for key, evidence in evidence_by_key.items():
        magnitudes[key] = text_magnitude(evidence, snapshot_content)

    contributions: list[Contribution] = []
    total = BASE_SCORE
    for spec in INDICATORS:
        magnitude = magnitudes.get(spec.key, 0.0)
        if magnitude <= 0:
            continue
        weight = weight_of(spec)
        points = spec.direction * weight * magnitude
        total += points
        contributions.append(
            Contribution(
                key=spec.key,
                title=spec.title,
                direction=spec.direction,
                weight=weight,
                magnitude=magnitude,
                points=points,
                evidence=evidence_by_key.get(spec.key, []),
                note=notes.get(spec.key, ""),
            )
        )

    score = round(min(max(total, 0.0), 100.0))
    contributions.sort(key=lambda item: abs(item.points), reverse=True)
    value = coverage(parsed_facts)
    confidence = confidence_of(value, parsed_facts)
    return DetectionScore(
        score=score,
        coverage=round(value, 3),
        confidence=confidence,
        category=category_of(score, confidence, verdict),
        contributions=contributions,
    )
