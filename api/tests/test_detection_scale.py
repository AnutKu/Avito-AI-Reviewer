import unittest
from unittest.mock import patch

from app.services import detection_scale as scale


def notebook(**overrides) -> dict:
    facts = {
        "path": "solution.ipynb",
        "code_cells": 10,
        "markdown_cells": 4,
        "code_chars": 5000,
        "markdown_chars": 1000,
        "unrun_cells": 0,
        "failed_cells": 0,
        "execution_counts": list(range(1, 11)),
    }
    facts.update(overrides)
    return facts


def parsed(notebooks=None, **overrides) -> dict:
    facts = {
        "notebooks": [notebook()] if notebooks is None else notebooks,
        "snapshot_chars": 12_000,
        "truncated": False,
    }
    facts.update(overrides)
    return facts


class ExecutionDisorderTest(unittest.TestCase):
    def test_clean_sequence_from_one_gives_nothing(self):
        magnitudes = scale.facts_magnitudes(parsed())

        self.assertEqual(magnitudes["execution_disorder"], 0.0)

    def test_restart_of_the_kernel_is_full_evidence(self):
        # Работа начата не с первой ячейки: сессия жила до того, что мы видим.
        magnitudes = scale.facts_magnitudes(
            parsed([notebook(execution_counts=list(range(7, 17)))])
        )

        self.assertEqual(magnitudes["execution_disorder"], 1.0)

    def test_out_of_order_counts_raise_the_magnitude(self):
        magnitudes = scale.facts_magnitudes(
            parsed([notebook(execution_counts=[1, 2, 3, 9, 4, 10, 5, 11])])
        )

        self.assertGreater(magnitudes["execution_disorder"], 0.0)

    def test_short_notebook_yields_no_facts_at_all(self):
        # На двух ячейках «порядок выполнения» — совпадение, а не наблюдение.
        magnitudes = scale.facts_magnitudes(
            parsed([notebook(code_cells=2, execution_counts=[1, 2])])
        )

        self.assertEqual(magnitudes, {})

    def test_messy_notebook_wins_over_clean_one(self):
        # Признак оправдательный: один живой ноутбук — уже след ручной работы.
        magnitudes = scale.facts_magnitudes(
            parsed([notebook(), notebook(path="b.ipynb", execution_counts=[9, 10, 11, 12, 13])])
        )

        self.assertEqual(magnitudes["execution_disorder"], 1.0)


class TextMagnitudeTest(unittest.TestCase):
    def test_three_confirmed_places_give_full_magnitude(self):
        snapshot = "alpha beta gamma delta"
        evidence = [{"quote": "alpha"}, {"quote": "beta"}, {"quote": "gamma"}]

        self.assertEqual(scale.text_magnitude(evidence, snapshot), 1.0)

    def test_unconfirmed_quote_lowers_magnitude_without_dropping_indicator(self):
        evidence = [{"quote": "alpha"}, {"quote": "выдумано"}, {"quote": "тоже выдумано"}]

        self.assertAlmostEqual(scale.text_magnitude(evidence, "alpha beta"), 1 / 3)

    def test_quote_is_matched_across_reformatted_whitespace(self):
        snapshot = "import   pandas\n\n   as pd"

        self.assertEqual(scale.text_magnitude([{"quote": "import pandas as pd"}], snapshot), 1 / 3)

    def test_fully_invented_evidence_contributes_nothing(self):
        self.assertEqual(scale.text_magnitude([{"quote": "нет такого"}], "alpha"), 0.0)


class ScoreTest(unittest.TestCase):
    def test_nothing_observed_stays_at_the_base(self):
        result = scale.compute(parsed_facts=parsed(), snapshot_content="x", indicators=[])

        self.assertEqual(result.score, scale.BASE_SCORE)

    def test_process_traces_lower_the_score(self):
        result = scale.compute(
            parsed_facts=parsed([notebook(execution_counts=list(range(7, 17)), unrun_cells=3)]),
            snapshot_content="x",
            indicators=[],
        )

        self.assertLess(result.score, scale.BASE_SCORE)
        self.assertTrue(all(item.direction < 0 for item in result.contributions))

    def test_generation_traces_raise_the_score(self):
        snapshot = "alpha beta gamma"
        result = scale.compute(
            parsed_facts=parsed(),
            snapshot_content=snapshot,
            indicators=[
                {
                    "key": "task_mismatch",
                    "note": "",
                    "evidence": [{"quote": "alpha"}, {"quote": "beta"}, {"quote": "gamma"}],
                }
            ],
        )

        self.assertEqual(result.score, scale.BASE_SCORE + 18)

    def test_facts_keys_from_the_model_are_ignored(self):
        # Величину признаков процесса даёт parsed_facts. Модель может только
        # приложить комментарий, и подменить ею наблюдение нельзя.
        result = scale.compute(
            parsed_facts=parsed(),
            snapshot_content="alpha",
            indicators=[{"key": "execution_disorder", "note": "", "evidence": [{"quote": "alpha"}]}],
        )

        self.assertEqual(result.score, scale.BASE_SCORE)
        self.assertEqual(result.contributions, [])

    def test_score_is_clamped_to_the_scale(self):
        snapshot = " ".join(f"w{index}" for index in range(60))
        indicators = [
            {
                "key": key,
                "note": "",
                "evidence": [{"quote": f"w{position * 3 + shift}"} for shift in range(3)],
            }
            for position, key in enumerate(scale.TEXT_KEYS)
        ]
        result = scale.compute(
            parsed_facts=parsed(), snapshot_content=snapshot, indicators=indicators
        )

        self.assertLessEqual(result.score, 100)

    def test_weights_can_be_overridden_from_config(self):
        snapshot = "alpha beta gamma"
        indicators = [
            {
                "key": "task_mismatch",
                "note": "",
                "evidence": [{"quote": "alpha"}, {"quote": "beta"}, {"quote": "gamma"}],
            }
        ]
        with patch.dict(
            "app.services.detection_scale.settings.detection_weights",
            {"task_mismatch": 40},
            clear=False,
        ):
            result = scale.compute(
                parsed_facts=parsed(), snapshot_content=snapshot, indicators=indicators
            )

        self.assertEqual(result.score, scale.BASE_SCORE + 40)


class CoverageTest(unittest.TestCase):
    def test_full_notebook_and_volume_give_high_confidence(self):
        value = scale.coverage(parsed())

        self.assertEqual(scale.confidence_of(value, parsed()), scale.CONFIDENCE_HIGH)

    def test_repository_without_notebooks_drops_to_medium(self):
        # Go-репозиторий или markdown-ответ: текстовые признаки работают,
        # свидетельств процесса нет вовсе.
        facts = parsed(notebooks=[])

        self.assertEqual(scale.confidence_of(scale.coverage(facts), facts), scale.CONFIDENCE_MEDIUM)

    def test_tiny_submission_is_not_reportable(self):
        facts = parsed(notebooks=[], snapshot_chars=900)
        result = scale.compute(parsed_facts=facts, snapshot_content="x", indicators=[])

        self.assertEqual(result.confidence, scale.CONFIDENCE_LOW)
        self.assertFalse(result.is_reportable)
        self.assertIsNone(result.category)

    def test_truncated_snapshot_cannot_reach_high(self):
        facts = parsed(truncated=True)

        self.assertNotEqual(
            scale.confidence_of(scale.coverage(facts), facts), scale.CONFIDENCE_HIGH
        )


class CategoryTest(unittest.TestCase):
    def test_bands_follow_the_documented_thresholds(self):
        self.assertEqual(scale.category_of(34, scale.CONFIDENCE_HIGH), scale.CATEGORY_NO_SIGNS)
        self.assertEqual(scale.category_of(35, scale.CONFIDENCE_HIGH), scale.CATEGORY_TOOL_ASSISTED)
        self.assertEqual(scale.category_of(70, scale.CONFIDENCE_HIGH), scale.CATEGORY_TOOL_ASSISTED)
        self.assertEqual(
            scale.category_of(71, scale.CONFIDENCE_HIGH), scale.CATEGORY_LIKELY_GENERATED
        )

    def test_low_confidence_leaves_the_work_uncategorised(self):
        self.assertIsNone(scale.category_of(88, scale.CONFIDENCE_LOW))


class VerdictCategoryTest(unittest.TestCase):
    """Категорию называет голосование прогонов; пороги — запасной путь."""

    def test_verdict_decides_the_category_over_the_thresholds(self):
        # Индекс 10 попал бы в no_signs по порогам, но большинство прогонов
        # сказало «ai». Число и вердикт отвечают на разные вопросы, и вердикт
        # отвечает именно на этот.
        self.assertEqual(
            scale.category_of(10, scale.CONFIDENCE_HIGH, "ai"),
            scale.CATEGORY_LIKELY_GENERATED,
        )
        self.assertEqual(
            scale.category_of(95, scale.CONFIDENCE_HIGH, "human"),
            scale.CATEGORY_NO_SIGNS,
        )

    def test_every_verdict_maps_onto_a_category(self):
        for verdict, category in scale.VERDICT_CATEGORY.items():
            self.assertEqual(scale.category_of(50, scale.CONFIDENCE_HIGH, verdict), category)

    def test_missing_verdict_falls_back_to_the_thresholds(self):
        # Прогон без голосования: старая запись или вызов из теста якорей.
        self.assertEqual(
            scale.category_of(88, scale.CONFIDENCE_HIGH, None),
            scale.CATEGORY_LIKELY_GENERATED,
        )

    def test_low_confidence_outranks_any_verdict(self):
        # Наблюдать было нечего: три прогона по пустому месту сходятся не лучше
        # одного, и категория не выставляется независимо от того, что они решили.
        self.assertIsNone(scale.category_of(10, scale.CONFIDENCE_LOW, "ai"))

    def test_verdict_does_not_move_the_number(self):
        facts = parsed()
        arguments = {"parsed_facts": facts, "snapshot_content": "x", "indicators": []}

        self.assertEqual(
            scale.compute(**arguments, verdict="ai").score,
            scale.compute(**arguments, verdict="human").score,
        )


if __name__ == "__main__":
    unittest.main()
