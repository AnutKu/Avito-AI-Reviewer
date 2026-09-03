"""Экспорт задания в двух проекциях.

view="student"  — то, что выдаётся студенту (без скрытой рубрики и эталона);
view="reviewer" — полная версия для ревьюера / реестра проверки (по умолчанию).
"""

from __future__ import annotations

from typing import Literal

from app.render import reviewer_md, student_brief_md, student_dict
from app.schemas import TaskDraftData

View = Literal["student", "reviewer"]


def to_dict(data: TaskDraftData, view: View = "reviewer") -> dict:
    if view == "student":
        return student_dict(data)
    d = data.model_dump()
    d["total_points"] = data.total_points
    return d


def to_markdown(data: TaskDraftData, view: View = "reviewer") -> str:
    if view == "student":
        return student_brief_md(data)
    return reviewer_md(data)
