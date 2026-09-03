"""Юнит-тесты чистой логики конвейера (без БД и HTTP)."""

from __future__ import annotations

from app.agents.roles import _normalize_points
from app.pipeline import apply_edits, build_score_matrix, consolidate_edits
from app.schemas import (
    Criterion,
    CriterionEdit,
    GradedCriterion,
    GraderOutput,
    RoundArtifact,
    TaskDraftData,
)


def _crit(key: str, pts: float, desc: str = "описание") -> Criterion:
    return Criterion(
        key=key,
        title=key.title(),
        description=desc,
        max_points=pts,
        check_kind="objective",
        evidence_hint="куда смотреть",
    )


def test_apply_edits_modify_add_remove():
    base = [_crit("a", 5), _crit("b", 3), _crit("c", 2)]
    edits = [
        CriterionEdit(
            id="E1",
            operation="modify",
            criterion_key="a",
            proposed_criterion=_crit("a", 6, "уточнено"),
            rationale="r",
            addresses=[],
            severity="high",
        ),
        CriterionEdit(
            id="E2",
            operation="remove",
            criterion_key="b",
            proposed_criterion=None,
            rationale="r",
            addresses=[],
            severity="low",
        ),
        CriterionEdit(
            id="E3",
            operation="add",
            criterion_key="d",
            proposed_criterion=_crit("d", 4),
            rationale="r",
            addresses=[],
            severity="medium",
        ),
    ]
    out = apply_edits(base, edits)
    assert [c.key for c in out] == ["a", "c", "d"]
    assert out[0].max_points == 6 and out[0].description == "уточнено"

    # выборочное применение
    out2 = apply_edits(base, edits, accepted_ids={"E1"})
    assert [c.key for c in out2] == ["a", "b", "c"]
    assert out2[0].max_points == 6


def test_consolidate_edits_relative_to_original():
    original = [_crit("a", 5), _crit("b", 5)]
    r1 = RoundArtifact(
        round_no=1,
        criteria_snapshot=original,
        solutions=[],
        gradings=[],
        findings=[],
        proposed_edits=[
            CriterionEdit(
                id="x",
                operation="modify",
                criterion_key="a",
                proposed_criterion=_crit("a", 5, "step1"),
                rationale="почему-1",
                addresses=["F1"],
                severity="high",
            )
        ],
        score_matrix={},
        converged=False,
        convergence_reason="",
    )
    recommended = [_crit("a", 5, "step2"), _crit("b", 5)]
    edits = consolidate_edits(original, recommended, [r1])
    assert len(edits) == 1
    e = edits[0]
    assert e.operation == "modify" and e.criterion_key == "a"
    assert e.before_snapshot == "описание"
    assert e.proposed_criterion.description == "step2"
    assert e.addresses == ["F1"] and e.severity == "high"


def test_build_score_matrix():
    crits = [_crit("a", 5), _crit("b", 5)]
    gradings = [
        GraderOutput(
            persona="p1",
            total_points=7,
            overall_comment="",
            scores=[
                GradedCriterion(
                    criterion_key="a",
                    points=4,
                    max_points=5,
                    rationale="",
                    evidence_quote="",
                    confidence=0.9,
                    decidable=True,
                ),
                GradedCriterion(
                    criterion_key="b",
                    points=3,
                    max_points=5,
                    rationale="",
                    evidence_quote="",
                    confidence=0.9,
                    decidable=True,
                ),
            ],
        ),
        GraderOutput(
            persona="p2",
            total_points=9,
            overall_comment="",
            scores=[
                GradedCriterion(
                    criterion_key="a",
                    points=5,
                    max_points=5,
                    rationale="",
                    evidence_quote="",
                    confidence=0.9,
                    decidable=True,
                ),
                GradedCriterion(
                    criterion_key="b",
                    points=4,
                    max_points=5,
                    rationale="",
                    evidence_quote="",
                    confidence=0.9,
                    decidable=True,
                ),
            ],
        ),
    ]
    m = build_score_matrix(crits, gradings)
    assert m["a"] == {"p1": 4.0, "p2": 5.0}
    assert m["b"] == {"p1": 3.0, "p2": 4.0}


def test_normalize_points_rescales_to_target():
    data = TaskDraftData(
        title="t",
        summary="s",
        statement_md="c",
        learning_objectives=["o"],
        reference_solution_md="ref",
        common_mistakes=["m"],
        criteria=[_crit("a", 3), _crit("b", 3), _crit("c", 3)],  # сумма 9
    )
    out = _normalize_points(data, 10)
    assert abs(out.total_points - 10) < 1e-6
