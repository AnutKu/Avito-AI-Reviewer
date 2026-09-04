"""Что из вопроса видит студент.

Единственный тест в наборе, падение которого означает утечку, а не регрессию:
`expected_points` — это то, что должен показать понимающий ответ, и попав в
выдачу студента вместе с вопросом, оно превращает опрос в тест с ответами на
обороте.
"""

import unittest

from app.serializers import STUDENT_QUESTION_FIELDS, student_question_data

QUESTION = {
    "id": "q1",
    "type": "explain_choice",
    "text": "Почему выбрана именно эта модель?",
    "anchor": "Ячейка 22",
    "expected_points": ["названа цена ошибки", "сравнение метрик осознанное"],
}


class StudentProjectionTest(unittest.TestCase):
    def test_expected_points_do_not_reach_the_student(self):
        self.assertNotIn("expected_points", student_question_data(QUESTION))

    def test_anchor_does_not_reach_the_student(self):
        # Якорь — место, к которому ревьюер привязал вопрос. Студенту он
        # подсказывает, где искать ответ, вместо того чтобы вспоминать.
        self.assertNotIn("anchor", student_question_data(QUESTION))

    def test_the_question_itself_survives(self):
        projected = student_question_data(QUESTION)

        self.assertEqual(projected["text"], QUESTION["text"])
        self.assertEqual(projected["id"], "q1")

    def test_a_new_field_in_the_contract_does_not_leak_by_default(self):
        # Ради этого здесь белый список, а не удаление лишнего: поле, о котором
        # проекция не знает, обязано не попадать наружу само по себе.
        projected = student_question_data({**QUESTION, "reviewer_note": "секрет"})

        self.assertEqual(set(projected), set(STUDENT_QUESTION_FIELDS))

    def test_missing_field_does_not_raise(self):
        # Засеянный или старый вопрос без части полей не должен ронять выдачу.
        self.assertEqual(student_question_data({"id": "q1"})["text"], "")
