"""Якоря шкалы детекции.

Размеченной выборки «списано / не списано» нет и не будет, поэтому шкалу
закрепляем якорями: две реальные работы, размеченные курсом по качеству, и одна
намеренно синтезированная «сгенерированная». Тест падает, если правка весов
переворачивает порядок между ними.

Что тест пиннит и чего не пиннит: арифметика, веса, покрытие и гейт — да;
поведение модели — нет. Текстовые признаки здесь подаются фикстурой, как если бы
их вернул провайдер, а цитаты берутся дословно из снапшота, чтобы проверка
подтверждения работала на настоящем тексте.
"""

import io
import json
import unittest
import zipfile
from pathlib import Path

from app.services import detection_scale as scale
from app.services.github import build_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "Product-part" / "01_Входящие" / "homework_examples" / "data_science"
HUMAN_WEAK = CORPUS / "Пример ДЗ. Курс _LLM_" / "Слабое решение.ipynb"
HUMAN_GOOD = CORPUS / "Пример ДЗ. Курс _LLM_" / "Хорошее решение" / "model_output_experiments.ipynb"


def snapshot_of(files: dict[str, bytes]):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, payload in files.items():
            bundle.writestr(f"repo-main/{name}", payload)
    return build_snapshot(buffer.getvalue())


def snapshot_of_file(path: Path):
    return snapshot_of({path.name: path.read_bytes()})


def real_quotes(content: str, count: int) -> list[dict]:
    """Дословные куски снапшота — чтобы проверка подтверждения не была фиктивной."""

    lines = [line.strip() for line in content.splitlines() if len(line.strip()) > 25]
    return [{"quote": line, "anchor": "Ячейка"} for line in lines[:count]]


def generated_notebook() -> bytes:
    """Ноутбук без следов процесса: ровный markdown, чистая история, много текста."""

    cells = []
    for index in range(1, 13):
        cells.append(
            {
                "cell_type": "markdown",
                "source": [
                    f"## Шаг {index}\n",
                    "В этом разделе мы импортируем необходимые библиотеки и подготавливаем "
                    "данные для дальнейшего анализа. Такой подход считается хорошей "
                    "практикой, поскольку он повышает читаемость и воспроизводимость "
                    "исследования, что особенно важно при работе в команде.\n",
                ],
            }
        )
        cells.append(
            {
                "cell_type": "code",
                "execution_count": index,
                "source": [
                    "import pandas as pd\n",
                    f"df_{index} = pd.DataFrame()\n",
                    "model = None\n",
                    "data = df_{}.copy()\n".format(index),
                ],
                "outputs": [],
            }
        )
    return json.dumps({"cells": cells}).encode()


class DetectionAnchorsTest(unittest.TestCase):
    @unittest.skipUnless(HUMAN_WEAK.exists(), "корпус примеров недоступен в этом окружении")
    def test_weak_human_solution_stays_in_the_clean_band(self):
        snapshot = snapshot_of_file(HUMAN_WEAK)
        indicators = [
            {"key": key, "note": "", "evidence": real_quotes(snapshot.content, 1)}
            for key in ("generic_naming", "style_uniformity")
        ]

        result = scale.compute(
            parsed_facts=snapshot.parsed_facts,
            snapshot_content=snapshot.content,
            indicators=indicators,
        )

        self.assertEqual(result.confidence, scale.CONFIDENCE_HIGH)
        self.assertLessEqual(result.score, 35)
        self.assertEqual(result.category, scale.CATEGORY_NO_SIGNS)

    @unittest.skipUnless(HUMAN_WEAK.exists(), "корпус примеров недоступен в этом окружении")
    def test_restart_and_unrun_cells_are_the_reason(self):
        snapshot = snapshot_of_file(HUMAN_WEAK)
        magnitudes = scale.facts_magnitudes(snapshot.parsed_facts)

        self.assertEqual(magnitudes["execution_disorder"], 1.0)
        self.assertGreater(magnitudes["unrun_cells"], 0.0)

    @unittest.skipUnless(HUMAN_GOOD.exists(), "корпус примеров недоступен в этом окружении")
    def test_short_good_solution_is_not_reportable_at_all(self):
        # Восемь ячеек, из них две с кодом: наблюдать нечего, и число ревьюер
        # не увидит. Гейт по покрытию, а не шкала, спасает работу от вывода.
        snapshot = snapshot_of_file(HUMAN_GOOD)

        result = scale.compute(
            parsed_facts=snapshot.parsed_facts,
            snapshot_content=snapshot.content,
            indicators=[],
        )

        self.assertEqual(result.confidence, scale.CONFIDENCE_LOW)
        self.assertFalse(result.is_reportable)
        self.assertIsNone(result.category)

    def test_generated_solution_crosses_the_upper_anchor(self):
        snapshot = snapshot_of({"solution.ipynb": generated_notebook()})
        indicators = [
            {"key": key, "note": "", "evidence": real_quotes(snapshot.content, 3)}
            for key in ("task_mismatch", "internal_contradiction", "unused_scaffolding")
        ]

        result = scale.compute(
            parsed_facts=snapshot.parsed_facts,
            snapshot_content=snapshot.content,
            indicators=indicators,
        )

        self.assertEqual(result.confidence, scale.CONFIDENCE_HIGH)
        self.assertGreaterEqual(result.score, 70)
        self.assertEqual(result.category, scale.CATEGORY_LIKELY_GENERATED)

    def test_ordering_between_anchors_holds(self):
        generated = snapshot_of({"solution.ipynb": generated_notebook()})
        generated_score = scale.compute(
            parsed_facts=generated.parsed_facts,
            snapshot_content=generated.content,
            indicators=[
                {"key": key, "note": "", "evidence": real_quotes(generated.content, 3)}
                for key in ("task_mismatch", "internal_contradiction", "unused_scaffolding")
            ],
        ).score

        if not HUMAN_WEAK.exists():
            self.skipTest("корпус примеров недоступен в этом окружении")
        weak = snapshot_of_file(HUMAN_WEAK)
        weak_score = scale.compute(
            parsed_facts=weak.parsed_facts,
            snapshot_content=weak.content,
            indicators=[],
        ).score

        self.assertGreater(generated_score, weak_score)


if __name__ == "__main__":
    unittest.main()
