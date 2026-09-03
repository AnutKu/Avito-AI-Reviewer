"""Deterministic replacement for the future AI review pipeline.

The UI and API use the same persisted entities that a real worker will fill later.
Replacing this module must not require changing the HTTP contracts.
"""

from sqlalchemy.orm import Session

from ..models import (
    AiSignal,
    AiStatus,
    Confidence,
    Review,
    ReviewerAction,
    ReviewItem,
    SignalDecision,
    SignalKind,
    Verdict,
)


MOCK_ITEMS = [
    {
        "key": "experiment_tracking",
        "title": "Трекинг экспериментов",
        "max_score": 3,
        "score": 3,
        "verdict": Verdict.PASSED,
        "confidence": Confidence.HIGH,
        "evidence": [
            {"quote": "mlflow.log_params(params)", "anchor": "Ячейка 12"},
            {"quote": "mlflow.log_metrics(metrics)", "anchor": "Ячейка 15"},
        ],
        "recommendation": "Трекинг параметров и метрик реализован полно.",
    },
    {
        "key": "runs_count",
        "title": "Не менее 20 запусков",
        "max_score": 2,
        "score": 2,
        "verdict": Verdict.PASSED,
        "confidence": Confidence.HIGH,
        "evidence": [{"quote": "Количество запусков: 24", "anchor": "MLflow runs"}],
        "recommendation": "Требование по числу экспериментов выполнено.",
    },
    {
        "key": "model_registry",
        "title": "Регистрация лучшей модели",
        "max_score": 2,
        "score": 1,
        "verdict": Verdict.PARTIAL,
        "confidence": Confidence.MEDIUM,
        "evidence": [
            {"quote": "mlflow.sklearn.log_model(model, artifact_path='model')", "anchor": "Ячейка 19"}
        ],
        "recommendation": "Артефакт сохранён, но явная регистрация в Model Registry не показана.",
    },
    {
        "key": "reproducibility",
        "title": "Воспроизводимость",
        "max_score": 2,
        "score": 1.5,
        "verdict": Verdict.PARTIAL,
        "confidence": Confidence.MEDIUM,
        "evidence": [{"quote": "random_state=42", "anchor": "Ячейка 7"}],
        "recommendation": "Seed модели задан; стоит также зафиксировать seed библиотек.",
    },
    {
        "key": "conclusions",
        "title": "Выводы по экспериментам",
        "max_score": 1,
        "score": 0.5,
        "verdict": Verdict.PARTIAL,
        "confidence": Confidence.LOW,
        "evidence": [{"quote": "Лучший результат показал Random Forest", "anchor": "Ячейка 22"}],
        "recommendation": "Добавить сравнение метрик и объяснить выбор итоговой модели.",
    },
]


def fill_mock_review(db: Session, review: Review, quality: float = 1.0) -> Review:
    """Persist a ready mock response. ``quality`` creates varied demo records."""

    review.ai_status = AiStatus.READY
    review.model = "mock/ai-review-v1"
    review.draft_feedback = (
        "Хорошая работа: эксперименты последовательно залогированы, а результат можно "
        "воспроизвести. Перед финальной сдачей зарегистрируйте лучшую модель в Model "
        "Registry и дополните вывод сравнением метрик."
    )
    review.raw_result = {
        "summary": "Основная часть выполнена, два критерия требуют внимания ревьюера.",
        "pipeline": ["extract", "grade", "signal", "feedback"],
        "mock": True,
    }
    for position, item in enumerate(MOCK_ITEMS):
        score = round(min(item["max_score"], item["score"] * quality), 1)
        db.add(
            ReviewItem(
                review=review,
                position=position,
                criterion_key=item["key"],
                criterion_title=item["title"],
                max_score=item["max_score"],
                ai_score=score,
                verdict=item["verdict"],
                confidence=item["confidence"],
                evidence=item["evidence"],
                recommendation=item["recommendation"],
                reviewer_action=ReviewerAction.PENDING,
            )
        )

    db.add_all(
        [
            AiSignal(
                review_id=review.id,
                kind=SignalKind.AI_USE,
                level=Confidence.MEDIUM,
                summary="Код стилистически однороден, но история выполнения содержит ручные итерации.",
                grounds=[
                    "Выполнение ячеек шло не по порядку",
                    "Есть два отладочных запуска с ошибкой",
                    "Markdown заметно короче сложных фрагментов кода",
                ],
                limitations=(
                    "Сигнал не доказывает использование генеративного AI. Он основан только "
                    "на наблюдаемых признаках и требует решения ревьюера."
                ),
                reviewer_decision=SignalDecision.PENDING,
            ),
            AiSignal(
                review_id=review.id,
                kind=SignalKind.UNDERSTANDING_RISK,
                level=Confidence.LOW,
                summary="Вывод по выбору модели объяснён слишком кратко.",
                grounds=["Сложный подбор гиперпараметров описан одним предложением"],
                limitations="Краткость объяснения сама по себе не означает отсутствия понимания.",
                reviewer_decision=SignalDecision.PENDING,
            ),
        ]
    )
    return review


def blitz_questions() -> list[dict]:
    return [
        {
            "id": "q1",
            "type": "explain_choice",
            "text": "Почему для итоговой модели вы выбрали Random Forest, а не модель с лучшим recall?",
            "selected": True,
        },
        {
            "id": "q2",
            "type": "what_if",
            "text": "Что изменится в результатах, если убрать фиксацию random_state?",
            "selected": True,
        },
        {
            "id": "q3",
            "type": "change_solution",
            "text": "Как бы вы зарегистрировали лучшую модель в MLflow Model Registry?",
            "selected": False,
        },
    ]
