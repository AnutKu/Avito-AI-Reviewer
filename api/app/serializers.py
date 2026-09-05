from datetime import datetime
from typing import Any

from .config import settings
from .models import (
    AiDetection,
    AiSignal,
    Assignment,
    BlitzSession,
    Review,
    ReviewItem,
    Submission,
)
from .services.blitz_telemetry import FLAG_TITLES


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# Поля критерия, которые видит студент. Градация («за что 0, за что 1, за что 2»)
# сюда не входит: по ней решение подгоняется под грейдинг, и в конструкторе
# заданий она с самого начала помечена как скрытая. Белый список, а не удаление
# лишнего — по той же причине, что и у вопросов блица ниже: новое поле рубрики
# по умолчанию не утекает.
STUDENT_CRITERION_FIELDS = ("key", "title", "max_score", "student_hint")


def public_criteria(criteria: list | None) -> list[dict]:
    return [
        {field: item[field] for field in STUDENT_CRITERION_FIELDS if field in item}
        for item in (criteria or [])
        if isinstance(item, dict)
    ]


def assignment_data(
    assignment: Assignment, rubric: Any = None, *, full: bool = False, authoring: bool = False
) -> dict:
    """Два разных «больше, чем видит студент», и они не совпадают.

    `full=True` — рубрика целиком, с градацией: это нужно ревьюеру, он по ней
    ставит балл. `authoring=True` — авторские блоки задания (эталон решения,
    заметки для калибровки, ревизия): это рабочий стол методиста. Ревьюеру
    эталон никуда не выводится, поэтому и не отправляется: данные, которые
    никто не показывает, — это утечка, которая ждёт своего экрана.
    """

    data = {
        "id": str(assignment.id),
        "title": assignment.title,
        "statement": assignment.statement,
        "deadline_at": iso(assignment.deadline_at),
        "effort_weight": assignment.effort_weight,
        "submission_channel": assignment.submission_channel,
        "course": assignment.course.title,
        "course_id": str(assignment.course_id),
        "published": assignment.published_at is not None,
        "published_at": iso(assignment.published_at),
        "rubric": (rubric.criteria if full else public_criteria(rubric.criteria)) if rubric else [],
        "max_score": rubric.max_score if rubric else None,
        "pass_score": rubric.pass_score if rubric else None,
    }
    if authoring:
        data["authoring"] = assignment.authoring or {}
        # Номер версии рубрики. Кабинет его не показывает как «v2» на кнопках —
        # версионирование внутреннее, — но результат AI-прогона обязан знать, к
        # какой ревизии он относится, иначе устаревший разбор не отличить.
        data["revision"] = rubric.version if rubric else 0
    return data


def ai_run_data(run: Any, recommendations: list | None = None) -> dict:
    """Прогон AI-персон. Рекомендации отдаются только там, где их запросили."""

    from .services.task_ai import run_stages

    data = {
        "id": str(run.id),
        "assignment_id": str(run.assignment_id),
        "revision": run.revision,
        "persona_type": run.persona_type,
        "status": run.status,
        "progress": run.progress,
        "stages": run_stages(
            status=run.status,
            progress=run.progress,
            persona_type=run.persona_type,
            samples=run.samples or 1,
            personas=len(run.personas or []) or 4,
        ),
        "summary": run.summary or None,
        "personas": run.personas or [],
        "samples": run.samples or 1,
        "metrics": run.metrics or {},
        "error": run.error,
        "created_at": iso(run.created_at),
        "completed_at": iso(run.completed_at),
    }
    if recommendations is not None:
        data["recommendations"] = [recommendation_data(item) for item in recommendations]
    return data


def recommendation_data(row: Any) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "target_type": row.target_type,
        "target_id": row.target_id,
        "target_field": row.target_field,
        "severity": row.severity,
        "problem": row.problem,
        "evidence": row.evidence or [],
        "original_value": row.original_value,
        "proposed_value": row.proposed_value,
        "final_value": row.final_value,
        "expected_effect": row.expected_effect,
        "status": row.status,
        "rejection_reason": row.rejection_reason,
        "kind": (row.payload or {}).get("finding", {}).get("kind") or "",
        "operation": (row.payload or {}).get("operation") or "",
    }


def submission_data(submission: Submission, reviewer: str | None = None) -> dict:
    return {
        "id": str(submission.id),
        "assignment_id": str(submission.assignment_id),
        "assignment": submission.assignment.title,
        "student": submission.student.full_name,
        "student_id": str(submission.student_id),
        "source_url": submission.source_url,
        "submitted_at": iso(submission.submitted_at),
        "deadline_at": iso(submission.assignment.deadline_at),
        "status": submission.status,
        "is_overdue": submission.is_overdue,
        "reviewer": reviewer,
    }


def item_data(item: ReviewItem, levels: list | None = None) -> dict:
    return {
        "id": str(item.id),
        "criterion_key": item.criterion_key,
        "criterion_title": item.criterion_title,
        "max_score": item.max_score,
        # Градация из рубрики, а не из ревью: ревьюер решает, сколько поставить,
        # и должен видеть, за что каждый балл даётся. У старых рубрик её нет —
        # тогда список пустой, и блок на экране не появляется.
        "levels": levels or [],
        "ai_score": item.ai_score,
        "verdict": item.verdict,
        "confidence": item.confidence,
        "evidence": item.evidence,
        "recommendation": item.recommendation,
        "reviewer_action": item.reviewer_action,
        "final_score": item.final_score,
        "reviewer_comment": item.reviewer_comment,
    }


def signal_data(signal: AiSignal) -> dict:
    return {
        "id": str(signal.id),
        "kind": signal.kind,
        "level": signal.level,
        "summary": signal.summary,
        "grounds": signal.grounds,
        "limitations": signal.limitations,
        "reviewer_decision": signal.reviewer_decision,
    }


def detection_data(detection: AiDetection | None) -> dict | None:
    """Индекс отдаётся наружу только при достаточном покрытии.

    Гейт стоит здесь, а не в интерфейсе: «мало данных» и «мало признаков» дают
    одинаково низкое число, и показать его — значит соврать. Экран получает
    reportable=false и печатает «признаков недостаточно», а не ноль.
    """

    if not detection:
        return None
    reportable = detection.status == "ready" and detection.confidence != "low"
    # Голосование лежит в raw_result: колонок под него в ai_detections нет и не
    # заводилось — новые колонки в существующей таблице проект не накатывает.
    raw = detection.raw_result or {}
    return {
        "id": str(detection.id),
        "status": detection.status,
        "score": int(detection.score) if reportable and detection.score is not None else None,
        "category": detection.category if reportable else None,
        # Вердикт и голоса — то же деление, что и категория, но с раскладкой по
        # прогонам: единогласное «AI» и перевес 2:1 читаются по-разному, и
        # склеивать их в одну подпись значило бы прятать от ревьюера разницу.
        "verdict": raw.get("verdict") if reportable else None,
        "votes": raw.get("votes", []) if reportable else [],
        "vote_agreement": raw.get("agreement") if reportable else None,
        "confidence": detection.confidence,
        "coverage": detection.coverage,
        "contributions": detection.contributions if reportable else [],
        "summary": detection.summary,
        "limitations": detection.limitations,
        "error": detection.error,
        "model": detection.model,
        "reportable": reportable,
        "blitz_threshold": settings.detection_blitz_threshold,
        "created_at": iso(detection.created_at),
    }


# Поля вопроса, которые видит студент. Список закрытый и перечислен явно:
# `expected_points` — это ответы на обороте, и утечь они могут ровно одним
# способом — если вопрос отдать целиком.
STUDENT_QUESTION_FIELDS = ("id", "type", "text")


def student_question_data(question: dict) -> dict:
    """Проекция вопроса для студента.

    Белый список, а не удаление лишнего: при удалении новое поле в контракте
    по умолчанию утекает, при белом списке — по умолчанию нет.
    """

    return {field: question.get(field, "") for field in STUDENT_QUESTION_FIELDS}


def blitz_data(session: BlitzSession | None, telemetry: dict | None = None) -> dict | None:
    """Полный вид опроса — только для ревьюера: здесь есть expected_points."""

    if not session:
        return None
    return {
        "id": str(session.id),
        "status": session.status,
        "questions": session.questions,
        "answers": session.answers,
        "ai_analysis": session.ai_analysis,
        "telemetry": telemetry,
        "telemetry_titles": FLAG_TITLES,
        "sent_at": iso(session.sent_at),
        "due_at": iso(session.due_at),
        "answered_at": iso(session.answered_at),
    }


def review_max_score(review: Review | None) -> float | None:
    """Максимум по рубрике этого ревью — знаменатель итогового балла.

    Раньше интерфейс писал «из 10» в разметке. Методист заводит критерии с
    любой суммой, так что это было просто неверно у любой рубрики, кроме
    десятибалльной. Отдаём настоящий максимум; где его нет (рубрика не
    привязана), возвращаем None, и знаменатель не показывается вовсе.
    """

    return review.rubric_version.max_score if review and review.rubric_version else None


def review_data(review: Review, include_internal: bool = True) -> dict:
    data = {
        "id": str(review.id),
        "submission_id": str(review.submission_id),
        "ai_status": review.ai_status,
        "final_score": review.final_score,
        "max_score": review_max_score(review),
        "final_feedback": review.final_feedback,
        "completed_at": iso(review.completed_at),
    }
    if include_internal:
        rubric = review.rubric_version
        levels_by_key = {
            criterion.get("key"): criterion.get("levels") or []
            for criterion in (rubric.criteria if rubric else [])
            if isinstance(criterion, dict)
        }
        data.update(
            {
                "model": review.model,
                "ai_error": review.ai_error,
                "summary": review.raw_result.get("summary", ""),
                "draft_feedback": review.draft_feedback,
                "is_demo": bool(review.raw_result.get("demo_data", False)),
                "items": [
                    item_data(item, levels_by_key.get(item.criterion_key)) for item in review.items
                ],
                "signals": [signal_data(signal) for signal in review.signals],
            }
        )
    return data
