"""Рендер задания в две проекции: студенческий бриф и полная рубрика ревьюера.

Одна точка правды для промптов (решатель видит бриф, грейдер/критик — рубрику),
экспорта и probe. Что попадает в бриф, а что скрыто — определяется здесь.
"""

from __future__ import annotations

import json

from app.schemas import Criterion, TaskDraftData

# --------------------------------------------------------------------------- #
#  Публичная проекция критериев
# --------------------------------------------------------------------------- #


def public_criteria(criteria: list[Criterion]) -> list[dict]:
    """Только то, что видит студент: имя, вес, одна фраза «что оценивается»."""
    return [
        {
            "key": c.key,
            "title": c.title,
            "max_points": c.max_points,
            "student_hint": c.student_hint,
            "check_kind": c.check_kind,
        }
        for c in criteria
    ]


def hidden_rubric_json(criteria: list[Criterion]) -> str:
    """Полная рубрика для грейдера/критика — со скрытыми полями."""
    return json.dumps([c.model_dump() for c in criteria], ensure_ascii=False)


# --------------------------------------------------------------------------- #
#  Студенческий бриф
# --------------------------------------------------------------------------- #


def student_brief_md(data: TaskDraftData, criteria: list[Criterion] | None = None) -> str:
    """Всё, что видит студент — и ничего сверх того."""
    crits = criteria if criteria is not None else data.criteria
    L: list[str] = [f"# {data.title}", "", data.summary, ""]

    if data.context_md.strip():
        L += ["## Контекст", "", data.context_md, ""]

    L += ["## Задача", "", data.statement_md, ""]

    if data.deliverables:
        L += ["## Что нужно сдать", ""]
        L += [f"{i}. {d}" for i, d in enumerate(data.deliverables, 1)]
        L.append("")

    if data.submission_format.strip():
        L += ["## Формат сдачи", "", data.submission_format, ""]

    L += ["## Критерии оценки", ""]
    L += ["| Критерий | Баллы | Что оценивается |", "|---|---|---|"]
    for c in crits:
        hint = (c.student_hint or "—").replace("\n", " ").replace("|", "\\|")
        L.append(f"| {c.title} | 0–{c.max_points} | {hint} |")
    L += ["", f"_Максимум: {round(sum(c.max_points for c in crits), 2)} баллов._", ""]
    if data.public_rubric_note.strip():
        L += [data.public_rubric_note, ""]

    if data.learning_objectives:
        L += ["## Чему научитесь", ""]
        L += [f"- {o}" for o in data.learning_objectives]
        L.append("")
    return "\n".join(L)


def reviewer_md(data: TaskDraftData, criteria: list[Criterion] | None = None) -> str:
    """Студенческий бриф + всё скрытое (для ревьюера / калибровки)."""
    crits = criteria if criteria is not None else data.criteria
    L = [student_brief_md(data, crits), "", "---", "", "# 🔒 Только для ревьюера", ""]

    L += ["## Рубрика (детально)", ""]
    for c in crits:
        kind = "объективный" if c.check_kind == "objective" else "субъективный"
        L += [f"### {c.title} (`{c.key}`) — 0–{c.max_points}, {kind}", "", c.description, ""]
        if c.evidence_hint.strip():
            L += [f"*Куда смотреть:* {c.evidence_hint}", ""]
        if c.expected_signals:
            L += ["*Признаки сильного ответа:*", ""]
            L += [f"- {s}" for s in c.expected_signals]
            L.append("")
        if c.rubric_levels:
            L += ["*Уровни:*", ""]
            L += [f"- {lv.points} — {lv.label}: {lv.descriptor}" for lv in c.rubric_levels]
            L.append("")

    L += ["## Эталонное решение", "", data.reference_solution_md, ""]
    L += ["## Типичные ошибки", ""]
    L += [f"- {m}" for m in data.common_mistakes]
    L.append("")
    if data.reviewer_notes.strip():
        L += ["## Заметки для калибровки", "", data.reviewer_notes, ""]
    return "\n".join(L)


def student_dict(data: TaskDraftData) -> dict:
    """JSON-проекция студенческого брифа (без скрытых полей)."""
    return {
        "title": data.title,
        "summary": data.summary,
        "context_md": data.context_md,
        "statement_md": data.statement_md,
        "deliverables": data.deliverables,
        "submission_format": data.submission_format,
        "public_rubric_note": data.public_rubric_note,
        "learning_objectives": data.learning_objectives,
        "criteria": public_criteria(data.criteria),
        "total_points": data.total_points,
    }
