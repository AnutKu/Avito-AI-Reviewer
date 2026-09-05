import json
import unittest
from collections import Counter
from unittest.mock import patch

from app.contracts import (
    DETECTION_INDICATORS,
    VERDICT_DEFINITIONS,
    VERDICT_SEVERITY,
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


def response(indicators, verdict: str = "human_ai_assisted") -> str:
    return json.dumps(
        {
            "indicators": indicators,
            "verdict": verdict,
            "summary": "Наблюдаются признаки однородного стиля.",
            "limitations": "Признаки не доказывают использование генеративного AI.",
        },
        ensure_ascii=False,
    )


def single_vote():
    """Голосование из одного прогона: проверки не про голоса читаются проще."""

    return patch("app.reviewer.settings.detection_votes", 1)


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
        fake = FakeClient(response([indicator("execution_disorder", ["df"])]))

        with single_vote(), self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=fake).detect(request())

    def test_probability_in_the_answer_is_rejected(self):
        payload = json.dumps(
            {
                "indicators": [],
                "verdict": "ai",
                "summary": "Похоже на генерацию.",
                "limitations": "Метод ограничен.",
                "score": 87,
            },
            ensure_ascii=False,
        )

        with single_vote(), self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(payload)).detect(request())

    def test_verdict_outside_the_three_categories_is_rejected(self):
        with single_vote(), self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(response([], verdict="maybe"))).detect(request())

    def test_duplicate_keys_are_rejected(self):
        payload = response(
            [
                indicator("generic_naming", ["df = pd.read_csv('data.csv')"]),
                indicator("generic_naming", ["model = RandomForestClassifier()"]),
            ]
        )

        with single_vote(), self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(payload)).detect(request())


class DetectionVoteTest(unittest.TestCase):
    """Голосование большинства: три прогона одной модели на одном промпте."""

    def test_verdict_catalog_matches_the_declared_keys(self):
        # Как и со справочником признаков: описания уходят в промпт, Literal
        # валидирует ответ. Разъехавшись, они дадут модели описание вердикта,
        # который контракт не примет.
        from app.contracts import DetectionVerdict

        self.assertEqual(set(VERDICT_DEFINITIONS), set(DetectionVerdict.__args__))
        self.assertEqual(set(VERDICT_SEVERITY), set(DetectionVerdict.__args__))

    def test_three_identical_calls_decide_one_verdict(self):
        fake = FakeClient(response([], verdict="human"))

        result = ZaiReviewer(client=fake).detect(request())

        calls = fake.chat.completions.calls
        self.assertEqual(len(calls), 3)
        # Голоса обязаны отличаться только выборкой модели: один и тот же
        # промпт, одна и та же модель. Иначе голосование считает разброс
        # формулировок вопроса, а не разброс мнений о решении.
        self.assertEqual([call["messages"] for call in calls], [calls[0]["messages"]] * 3)
        self.assertEqual({call["model"] for call in calls}, {"glm-5.3-flash"})
        self.assertEqual(result.vote.verdict, "human")
        self.assertEqual(result.vote.agreement, 3)

    def test_majority_wins_over_a_single_outlier(self):
        fake = FakeClient(
            [response([], verdict="ai"), response([], verdict="ai"), response([], verdict="human")]
        )

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.vote.verdict, "ai")
        self.assertEqual(result.vote.agreement, 2)
        self.assertEqual(Counter(result.vote.votes), Counter(["ai", "ai", "human"]))

    def test_full_disagreement_settles_on_the_middle_verdict(self):
        # 1-1-1: большинства нет. Середина — не компромисс ради компромисса:
        # любое другое правило на ничьей двигало бы вывод либо в обвинение,
        # либо в оправдание по тому, чей голос пришёл первым.
        fake = FakeClient(
            [
                response([], verdict="human"),
                response([], verdict="human_ai_assisted"),
                response([], verdict="ai"),
            ]
        )

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.vote.verdict, "human_ai_assisted")
        self.assertEqual(result.vote.agreement, 1)

    def test_two_way_tie_takes_the_less_severe_verdict(self):
        fake = FakeClient([response([], verdict="human"), response([], verdict="ai")])

        with patch("app.reviewer.settings.detection_votes", 2):
            result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.vote.verdict, "human")

    def test_result_comes_from_a_run_that_voted_with_the_majority(self):
        # Отчёт не склеивается из трёх: признаки и вердикт внутри одного
        # прогона согласованы, а у смеси эта связь теряется — под выводом
        # «человек» лежало бы обоснование прогона, решившего «AI».
        fake = FakeClient(
            [
                response([indicator("generic_naming", ["df = pd.read_csv('data.csv')"])], "ai"),
                response([], verdict="human"),
                response([], verdict="human"),
            ]
        )

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.vote.verdict, "human")
        self.assertEqual(result.result.verdict, "human")
        self.assertEqual(result.result.indicators, [])

    def test_failed_vote_does_not_lose_the_whole_run(self):
        fake = FakeClient(
            [RuntimeError("сеть моргнула"), response([], verdict="ai"), response([], verdict="ai")]
        )

        result = ZaiReviewer(client=fake).detect(request())

        self.assertEqual(result.vote.verdict, "ai")
        self.assertEqual(result.vote.votes, ["ai", "ai"])
        self.assertEqual(result.vote.agreement, 2)

    def test_run_fails_only_when_no_vote_arrives(self):
        fake = FakeClient([RuntimeError("провайдер недоступен")])

        with self.assertRaises(RuntimeError):
            ZaiReviewer(client=fake).detect(request())

    def test_tokens_of_every_vote_are_billed(self):
        # Три вызова, списанные как один, занижали бы стоимость прогона втрое.
        result = ZaiReviewer(client=FakeClient(response([], verdict="human"))).detect(request())

        self.assertEqual(result.metadata.prompt_tokens, 300)
        self.assertEqual(result.metadata.completion_tokens, 150)


if __name__ == "__main__":
    unittest.main()
