"""Обратимое маскирование перед отправкой в Z.AI.

Тесты идут без torch и без весов: `_ModelMasker` подменяется детектором на
регулярках. Проверяется не качество NER — оно свойство чекпоинта, — а контракт
слоя: что уходит наружу, что возвращается обратно и что происходит, когда
маскирование включено, но не работает.
"""

import json
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from app import masking


@dataclass(frozen=True)
class FakeSpan:
    start: int
    end: int
    label: str
    # Как у настоящего Span: кто нашёл и с какой уверенностью. У спанов
    # детерминированного слоя score равен None — у регулярки нет вероятности.
    source: str = "ner"
    score: float | None = 0.99


class FakeDetector:
    """Находит заранее известные значения — как если бы их разметила модель.

    Спан покрывает ровно значение и ничего вокруг: настоящий Detector
    возвращает такие же, и подмена не должна быть удобнее оригинала.
    """

    def __init__(self, known: list[tuple]):
        # (значение, метка) или (значение, метка, источник, уверенность)
        self.known = [row if len(row) == 4 else (*row, "ner", 0.99) for row in known]

    def spans(self, text):
        found = []
        for value, label, source, score in self.known:
            start = 0
            while (at := text.find(value, start)) != -1:
                found.append(FakeSpan(at, at + len(value), label, source, score))
                start = at + len(value)
        # Пересечения снимаются так же, как в predict.merge: левее и длиннее
        # побеждает. Без этого «Человек1» нашёлся бы внутри «Человек11», а
        # настоящий Detector таких спанов не отдаёт.
        found.sort(key=lambda span: (span.start, -(span.end - span.start)))
        out = []
        for span in found:
            if out and span.start < out[-1].end:
                continue
            out.append(span)
        return out


def masker(known, labels=None, min_score=0.6, min_length=3):
    """Слой с подставным детектором: без torch и без весов."""

    layer = masking._ModelMasker(
        bundle=None,
        device="cpu",
        labels=frozenset(labels if labels is not None else {row[1] for row in known}),
        min_score=min_score,
        min_length=min_length,
    )
    layer._detector = FakeDetector(known)
    return layer


PII = [("Петров", "PERSON"), ("Xt7#pQm2Zr", "PASSWORD"), ("svc_billing", "LOGIN")]


class MaskingTest(unittest.TestCase):
    def test_provider_sees_placeholder_instead_of_the_value(self):
        result = masker(PII).mask("Работу сдал Петров, пароль Xt7#pQm2Zr")

        self.assertNotIn("Петров", result.text)
        self.assertNotIn("Xt7#pQm2Zr", result.text)
        self.assertEqual(result.text, "Работу сдал [[PERSON_1]], пароль [[PASSWORD_1]]")

    def test_hyperparameters_stay_readable(self):
        # Ради этого из политики убрана метка SECRET: с ней прогон по двум
        # настоящим ноутбукам курса маскировал имена моделей и голые числа —
        # 29 спанов из 33 и ни одного настоящего секрета.
        text = "epochs = 10, seed = 42, model = Qwen3ForCausalLM, пароль Xt7#pQm2Zr"

        result = masker(PII).mask(text)

        self.assertIn("epochs = 10, seed = 42, model = Qwen3ForCausalLM", result.text)
        self.assertNotIn("Xt7#pQm2Zr", result.text)

    def test_numbering_is_per_label(self):
        # Сквозная нумерация давала PERSON_1 рядом с LOGIN_2, и это читается как
        # последовательность, а не как «первый человек, первый логин».
        known = [("Петров", "PERSON"), ("Иванов", "PERSON"), ("svc", "LOGIN")]

        result = masker(known).mask("Петров svc Иванов")

        self.assertEqual(result.text, "[[PERSON_1]] [[LOGIN_1]] [[PERSON_2]]")

    def test_the_same_value_keeps_the_same_placeholder(self):
        # Иначе модель видит двух разных людей там, где один, и рассуждает о
        # работе неверно.
        result = masker(PII).mask("Петров и ещё раз Петров")

        self.assertEqual(result.hits, 1)
        self.assertEqual(result.text.count("[[PERSON_1]]"), 2)

    def test_answer_comes_back_with_real_values(self):
        result = masker(PII).mask("пароль Xt7#pQm2Zr у Петров")

        answer = '{"quote": "пароль [[PASSWORD_1]]", "who": "[[PERSON_1]]"}'

        self.assertEqual(
            result.restore(answer), '{"quote": "пароль Xt7#pQm2Zr", "who": "Петров"}'
        )

    def test_restore_survives_two_digit_numbering(self):
        # «PERSON_1» — префикс «PERSON_10»: замена от коротких к длинным съела бы
        # ноль и оставила висячий символ в ответе.
        known = [(f"Человек{n}", "PERSON") for n in range(11, 0, -1)]
        result = masker(known).mask(" ".join(value for value, _ in known))

        self.assertEqual(result.restore(result.text), result.source)
        self.assertEqual(result.restore("[[PERSON_10]]"), "Человек2")

    def test_round_trip_returns_exactly_the_source(self):
        source = "Стенд svc_billing / Xt7#pQm2Zr на месте"

        result = masker(PII).mask(source)

        self.assertEqual(result.restore(result.text), source)

    def test_labels_outside_the_policy_are_left_alone(self):
        known = [("Петров", "PERSON"), ("Сбербанк", "ORGANIZATION")]

        result = masker(known, labels={"PERSON"}).mask("Петров из Сбербанк")

        self.assertEqual(result.text, "[[PERSON_1]] из Сбербанк")

    def test_empty_text_needs_no_model(self):
        layer = masking._ModelMasker(bundle=None, device="cpu", labels=frozenset({"PERSON"}))
        # Детектор не подставлен: если слой полезет его грузить — упадёт.
        self.assertEqual(layer.mask("   ").hits, 0)

    def test_low_confidence_ner_span_is_not_masked(self):
        # На коде NER заражается контекстом: после настоящей строки с паролем
        # она метит PASSWORD и на соседних. Замерено: мусор идёт с 0.52,
        # настоящие ПДн — с 0.67 и выше.
        known = [("Xt7#pQm2Zr", "PASSWORD", "both", None), ("seed = 42", "PASSWORD", "ner", 0.52)]

        result = masker(known).mask('password = "Xt7#pQm2Zr"\nseed = 42')

        self.assertIn("[[PASSWORD_1]]", result.text)
        self.assertIn("seed = 42", result.text)

    def test_deterministic_span_ignores_the_threshold(self):
        # У регулярки нет вероятности, и резать её порогом нечем: score None —
        # это «правило сработало», а не «уверенность нулевая».
        known = [("Xt7#pQm2Zr", "PASSWORD", "regex", None)]

        result = masker(known, min_score=0.99).mask('password = "Xt7#pQm2Zr"')

        self.assertNotIn("Xt7#pQm2Zr", result.text)

    def test_one_letter_span_is_not_a_secret(self):
        # NER рвёт границы: 's' внутри 'epochs' приезжает как PASSWORD и портит
        # слово, ничего не защищая.
        known = [("s", "PASSWORD", "ner", 0.62)]

        result = masker(known).mask("epochs = 10")

        self.assertEqual(result.text, "epochs = 10")

    def test_leftover_placeholder_is_visible(self):
        # Модель может исказить плейсхолдер, и он доедет до экрана как есть.
        # Утечки тут нет, но знать об этом надо.
        self.assertEqual(masking.leftovers("текст [[PERSON_1]] и [[LOGIN_2]]"),
                         ["[[LOGIN_2]]", "[[PERSON_1]]"])
        self.assertEqual(masking.leftovers("чистый текст"), [])


class MaskingPolicyTest(unittest.TestCase):
    def test_disabled_layer_changes_nothing(self):
        with patch("app.masking.settings.masking_enabled", False):
            masking._masker = None
            result = masking.mask("пароль qwerty у Петрова")

        self.assertEqual(result.text, "пароль qwerty у Петрова")
        self.assertEqual(result.hits, 0)
        masking._masker = None

    def test_enabled_but_missing_bundle_refuses_to_send(self):
        """Главное свойство слоя: он отказывает закрыто.

        Молча отправить неотмаскированное, потому что модель не нашлась, —
        ровно то, ради чего слой и заводился.
        """

        layer = masking._ModelMasker(
            bundle=masking.Path("/нет/такого/каталога"), device="cpu", labels=frozenset({"PERSON"})
        )

        with self.assertRaises(masking.MaskingUnavailable):
            layer.mask("пароль qwerty")

    def test_status_does_not_load_the_weights(self):
        with patch("app.masking.settings.masking_enabled", True), \
             patch("app.masking.settings.masking_model_path", "/нет/такого/каталога"):
            report = masking.status()

        self.assertTrue(report["enabled"])
        self.assertFalse(report["bundle_present"])


class ProviderNeverSeesRawTest(unittest.TestCase):
    """Сквозная проверка через настоящий detect(): что ушло и что вернулось.

    Тесты выше проверяют слой сам по себе; этот — что он действительно стоит на
    пути к провайдеру, а не просто существует рядом.
    """

    SOLUTION = 'password = "Xt7#pQm2Zr"\ndf = pd.read_csv("churn.csv")\n'

    def _detect(self, quote: str):
        from app.contracts import AssignmentInput, DetectionRequest, SnapshotInput
        from app.reviewer import ZaiReviewer
        from test_reviewer import FakeClient

        answer = json.dumps(
            {
                "indicators": [
                    {
                        "key": "generic_naming",
                        "evidence": [{"quote": quote, "anchor": "solution.py"}],
                        "note": "Наблюдение по тексту решения.",
                    }
                ],
                "verdict": "human",
                "summary": "Разбор решения.",
                "limitations": "Метод ограничен.",
            },
            ensure_ascii=False,
        )
        fake = FakeClient(answer)
        request = DetectionRequest(
            assignment=AssignmentInput(title="MLflow", statement="Проведите эксперименты"),
            snapshot=SnapshotInput(content=self.SOLUTION, parsed_facts={}),
        )
        layer = masker(PII)
        with patch("app.reviewer.settings.detection_votes", 1), \
             patch("app.reviewer.masking.mask", layer.mask):
            result = ZaiReviewer(client=fake).detect(request)
        sent = "\n".join(m["content"] for m in fake.chat.completions.kwargs["messages"])
        return sent, result

    def test_secret_does_not_reach_the_provider(self):
        sent, _ = self._detect('password = "[[PASSWORD_1]]"')

        self.assertNotIn("Xt7#pQm2Zr", sent)
        self.assertIn("[[PASSWORD_1]]", sent)
        # Всё остальное уходит как есть: маскируется значение, а не решение.
        self.assertIn('df = pd.read_csv("churn.csv")', sent)

    def test_reviewer_gets_the_real_quote_back(self):
        # Ради этого маскирование обратимое: на цитатах держится проверяемость
        # разбора, и [[PASSWORD_1]] на экране ревьюера доказывал бы ничего.
        _, result = self._detect('password = "[[PASSWORD_1]]"')

        quote = result.result.indicators[0].evidence[0].quote
        self.assertEqual(quote, 'password = "Xt7#pQm2Zr"')

    def test_quote_that_stayed_masked_does_not_survive_verification(self):
        """Модель исказила плейсхолдер — цитата не подтвердится и отпадёт.

        Отказ закрытый: непроверенное основание не доезжает до ревьюера, а не
        доезжает под видом проверенного.
        """

        _, result = self._detect('password = "[[PASSWORD_404]]"')

        self.assertEqual(result.result.indicators, [])


if __name__ == "__main__":
    unittest.main()
