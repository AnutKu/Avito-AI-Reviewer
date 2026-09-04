import json
import unittest

from app.contracts import (
    DETECTION_INDICATORS,
    AssignmentInput,
    DetectionRequest,
    SnapshotInput,
)
from app.reviewer import ZaiInvalidResponse, ZaiReviewer

from test_reviewer import FakeClient

SOLUTION = (
    "import pandas as pd\n"
    "df = pd.read_csv('data.csv')\n"
    "# Импортируем библиотеки для работы с данными\n"
    "model = RandomForestClassifier()\n"
)


def request(solution: str = SOLUTION) -> DetectionRequest:
    return DetectionRequest(
        assignment=AssignmentInput(
            title="MLflow",
            statement="Проведите эксперименты",
        ),
        snapshot=SnapshotInput(content=solution, parsed_facts={"notebooks": []}),
    )


def response(indicators) -> str:
    return json.dumps(
        {
            "indicators": indicators,
            "summary": "Наблюдаются признаки однородного стиля.",
            "limitations": "Признаки не доказывают использование генеративного AI.",
        },
        ensure_ascii=False,
    )


def indicator(key: str, quotes: list[str]) -> dict:
    return {
        "key": key,
        "evidence": [{"quote": quote, "anchor": "solution.py"} for quote in quotes],
        "note": "Наблюдение по тексту решения.",
    }


class DetectionContractTest(unittest.TestCase):
    def test_catalog_matches_the_declared_keys(self):
        # Справочник уходит в промпт, Literal валидирует ответ: разъехавшись,
        # они дадут модели описание признака, который контракт не примет.
        from app.contracts import DetectionIndicatorKey

        self.assertEqual(set(DETECTION_INDICATORS), set(DetectionIndicatorKey.__args__))

    def test_detection_asks_for_json_and_validates_result(self):
        fake = FakeClient(response([indicator("generic_naming", ["df = pd.read_csv('data.csv')"])]))

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.result.indicators[0].key, "generic_naming")
        self.assertEqual(fake.chat.completions.kwargs["response_format"], {"type": "json_object"})

    def test_empty_indicator_list_is_a_valid_answer(self):
        result = ZaiReviewer(client=FakeClient(response([]))).detect(request())

        self.assertEqual(result.result.indicators, [])

    def test_invented_quote_is_dropped_from_evidence(self):
        fake = FakeClient(
            response([indicator("generic_naming", ["df = pd.read_csv('data.csv')", "нет такого"])])
        )

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(len(result.result.indicators[0].evidence), 1)

    def test_indicator_without_a_single_confirmed_quote_disappears(self):
        fake = FakeClient(response([indicator("generic_naming", ["выдуманная цитата"])]))

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.result.indicators, [])

    def test_quote_survives_reformatted_whitespace(self):
        fake = FakeClient(response([indicator("style_uniformity", ["import  pandas   as pd"])]))

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(len(result.result.indicators), 1)

    def test_process_indicators_are_not_accepted_from_the_model(self):
        # execution_disorder считает core api из parsed_facts. Модель не должна
        # иметь возможности подменить наблюдение собственным впечатлением.
        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(response([indicator("execution_disorder", ["df"])]))).detect(
                request()
            )

    def test_probability_in_the_answer_is_rejected(self):
        payload = json.dumps(
            {
                "indicators": [],
                "summary": "Похоже на генерацию.",
                "limitations": "Метод ограничен.",
                "score": 87,
            },
            ensure_ascii=False,
        )

        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(payload)).detect(request())

    def test_duplicate_keys_are_rejected(self):
        payload = response(
            [
                indicator("generic_naming", ["df = pd.read_csv('data.csv')"]),
                indicator("generic_naming", ["model = RandomForestClassifier()"]),
            ]
        )

        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(payload)).detect(request())


if __name__ == "__main__":
    unittest.main()
