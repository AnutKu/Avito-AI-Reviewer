import json
import unittest

from app.contracts import (
    AnswerInput,
    AssignmentInput,
    BlitzAnalysisRequest,
    BlitzQuestion,
    BlitzQuestionsRequest,
    SnapshotInput,
)
from app.reviewer import ZaiInvalidResponse, ZaiReviewer

from test_reviewer import FakeClient

SOLUTION = (
    "import pandas as pd\n"
    "df = pd.read_csv('data.csv')\n"
    "model = RandomForestClassifier(random_state=42)\n"
)

ASSIGNMENT = AssignmentInput(title="MLflow", statement="Проведите эксперименты")


def questions_request(count: int = 3, focus: list[str] | None = None) -> BlitzQuestionsRequest:
    return BlitzQuestionsRequest(
        assignment=ASSIGNMENT,
        snapshot=SnapshotInput(content=SOLUTION, parsed_facts={"notebooks": []}),
        count=count,
        focus=focus or [],
    )


def question(question_id: str = "q1") -> dict:
    return {
        "id": question_id,
        "type": "explain_choice",
        "text": "Почему для итоговой модели выбран Random Forest?",
        "anchor": "Ячейка 3",
        "expected_points": ["названа цена ошибки в задаче"],
    }


def analysis_request(*question_ids: str, **texts: str) -> BlitzAnalysisRequest:
    ids = question_ids or ("q1",)
    return BlitzAnalysisRequest(
        assignment=ASSIGNMENT,
        questions=[BlitzQuestion(**question(key)) for key in ids],
        answers=[AnswerInput(question_id=key, text=texts.get(key, "")) for key in ids],
    )


def analysis_response(assessments) -> str:
    return json.dumps(
        {
            "assessments": assessments,
            "summary": "Ответы согласуются с решением.",
            "limitations": "Разбор не показывает, кто именно писал код.",
        },
        ensure_ascii=False,
    )


class QuestionGenerationTest(unittest.TestCase):
    def test_questions_are_generated_and_validated(self):
        fake = FakeClient(json.dumps({"questions": [question()]}, ensure_ascii=False))

        response = ZaiReviewer(client=fake).blitz_questions(questions_request())

        self.assertEqual(response.result.questions[0].anchor, "Ячейка 3")
        self.assertEqual(fake.chat.completions.kwargs["response_format"], {"type": "json_object"})

    def test_solution_is_wrapped_as_untrusted_data(self):
        fake = FakeClient(json.dumps({"questions": [question()]}, ensure_ascii=False))

        ZaiReviewer(client=fake).blitz_questions(questions_request())

        prompt = fake.chat.completions.kwargs["messages"][1]["content"]
        self.assertIn("<student_solution>", prompt)
        self.assertIn("</student_solution>", prompt)

    def test_observed_indicators_are_passed_as_aim(self):
        fake = FakeClient(json.dumps({"questions": [question()]}, ensure_ascii=False))

        ZaiReviewer(client=fake).blitz_questions(questions_request(focus=["generic_naming"]))

        self.assertIn("generic_naming", fake.chat.completions.kwargs["messages"][1]["content"])

    def test_extra_questions_are_trimmed_to_the_requested_count(self):
        # Просили два, модель прислала три: лишний вопрос ревьюер не заказывал.
        fake = FakeClient(
            json.dumps({"questions": [question("q1"), question("q2"), question("q3")]}, ensure_ascii=False)
        )

        response = ZaiReviewer(client=fake).blitz_questions(questions_request(count=2))

        self.assertEqual([item.id for item in response.result.questions], ["q1", "q2"])

    def test_question_without_expected_points_is_rejected(self):
        # Без них разбор ответа не с чем сверять, а ревьюеру нечего читать.
        broken = {**question(), "expected_points": []}
        fake = FakeClient(json.dumps({"questions": [broken]}, ensure_ascii=False))

        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=fake).blitz_questions(questions_request())

    def test_duplicate_ids_are_rejected(self):
        fake = FakeClient(
            json.dumps({"questions": [question("q1"), question("q1")]}, ensure_ascii=False)
        )

        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=fake).blitz_questions(questions_request())


class AnalysisTest(unittest.TestCase):
    def test_grounds_absent_from_the_answer_are_dropped(self):
        # Основание, которого в ответе нет, ревьюер проверить не может — оно
        # только придаёт выводу вид проверенного.
        fake = FakeClient(
            analysis_response(
                [
                    {
                        "question_id": "q1",
                        "verdict": "consistent",
                        "grounds": ["выбрал за устойчивость", "студент явно понимает bias-variance"],
                        "note": "Ответ по существу.",
                    }
                ]
            )
        )

        response = ZaiReviewer(client=fake).blitz_analysis(
            analysis_request("q1", q1="Я выбрал за устойчивость к выбросам.")
        )

        self.assertEqual(response.result.assessments[0].grounds, ["выбрал за устойчивость"])

    def test_quote_from_another_answer_does_not_count(self):
        # Основание должно указывать на то место, о котором идёт речь.
        fake = FakeClient(
            analysis_response(
                [
                    {
                        "question_id": "q1",
                        "verdict": "consistent",
                        "grounds": ["ответ на второй вопрос"],
                        "note": "Ответ по существу.",
                    },
                    {
                        "question_id": "q2",
                        "verdict": "consistent",
                        "grounds": [],
                        "note": "Ответ по существу.",
                    },
                ]
            )
        )

        response = ZaiReviewer(client=fake).blitz_analysis(
            analysis_request("q1", "q2", q1="совсем про другое", q2="ответ на второй вопрос")
        )

        self.assertEqual(response.result.assessments[0].grounds, [])

    def test_line_breaks_do_not_break_matching(self):
        # Студент перенёс строку посреди фразы; цитата от этого не перестаёт
        # быть его словами.
        fake = FakeClient(
            analysis_response(
                [
                    {
                        "question_id": "q1",
                        "verdict": "partial",
                        "grounds": ["за устойчивость к выбросам"],
                        "note": "Ответ поверхностный.",
                    }
                ]
            )
        )

        response = ZaiReviewer(client=fake).blitz_analysis(
            analysis_request("q1", q1="Выбрал\n  за   устойчивость\nк выбросам.")
        )

        self.assertEqual(response.result.assessments[0].grounds, ["за устойчивость к выбросам"])

    def test_assessment_of_a_question_that_was_never_asked_is_rejected(self):
        fake = FakeClient(
            analysis_response(
                [
                    {
                        "question_id": "q9",
                        "verdict": "inconsistent",
                        "grounds": [],
                        "note": "Ответ не по теме.",
                    }
                ]
            )
        )

        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=fake).blitz_analysis(analysis_request("q1", q1="ответ"))

    def test_answers_are_wrapped_as_untrusted_data(self):
        fake = FakeClient(
            analysis_response(
                [{"question_id": "q1", "verdict": "empty", "grounds": [], "note": "Ответа нет."}]
            )
        )

        ZaiReviewer(client=fake).blitz_analysis(analysis_request("q1", q1="ответ"))

        prompt = fake.chat.completions.kwargs["messages"][1]["content"]
        self.assertIn('<student_answer id="q1">', prompt)

    def test_telemetry_has_no_way_into_the_prompt(self):
        # Контракт разбора не принимает поведенческих данных: как студент себя
        # вёл и что он написал — разные свидетельства, и смешивать их в одном
        # промпте значит позволить одному подкрасить другое.
        with self.assertRaises(ValueError):
            BlitzAnalysisRequest(
                assignment=ASSIGNMENT,
                questions=[BlitzQuestion(**question())],
                answers=[AnswerInput(question_id="q1", text="ответ")],
                telemetry={"paste_dominant": True},
            )
