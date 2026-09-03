"""Тесты графа валидации напрямую (оффлайн-LLM, без БД и HTTP)."""

from __future__ import annotations

from app.graph.runtime import close_run, open_run
from app.pipeline import run_validation
from app.schemas import Criterion, ValidationConfigIn

STATEMENT = "Реализовать пул воркеров на Go с graceful shutdown."


def _criteria() -> list[Criterion]:
    return [
        Criterion(
            key="functional-correctness",
            title="Корректность",
            description="Все требования условия выполнены.",
            max_points=6,
            check_kind="objective",
            evidence_hint="сверить с условием",
        ),
        Criterion(
            key="readable-code",
            title="Читаемость кода",
            description="Код человекочитаемый и в хорошем стиле, как на воркшопе.",
            max_points=4,
            check_kind="subjective",
            evidence_hint="бегло просмотреть файлы",
        ),
    ]


async def test_graph_converges_in_two_rounds():
    res = await run_validation(
        cfg=ValidationConfigIn(max_rounds=3),
        statement_md=STATEMENT,
        criteria=_criteria(),
    )
    assert len(res.rounds) == 2
    assert res.rounds[0].converged is False
    assert res.rounds[1].converged is True
    assert res.converged is True
    assert res.proposed_edits, "ожидались правки относительно исходной рубрики"
    assert res.metrics.llm_calls > 0


async def test_round_accumulators_reset_between_rounds():
    """Во 2-м раунде solutions/gradings ровно по числу профилей, а не накопленные."""
    personas = ["diligent_strong", "minimalist_weak", "rule_lawyer"]
    res = await run_validation(
        cfg=ValidationConfigIn(max_rounds=2, personas=personas),
        statement_md=STATEMENT,
        criteria=_criteria(),
    )
    for rd in res.rounds:
        assert len(rd.solutions) == len(personas)
        assert len(rd.gradings) == len(personas)


async def test_stops_on_round_limit_without_convergence():
    res = await run_validation(
        cfg=ValidationConfigIn(max_rounds=1),
        statement_md=STATEMENT,
        criteria=_criteria(),
    )
    assert len(res.rounds) == 1
    assert res.converged is False
    assert "лимит раундов" in res.summary


async def test_graph_can_start_from_idea():
    """Узел generate: валидация прямо из идеи, без готовых критериев."""
    from app.schemas import CourseIdeaIn

    res = await run_validation(
        cfg=ValidationConfigIn(max_rounds=1),
        idea=CourseIdeaIn(idea="Научить писать идемпотентные обработчики вебхуков", track="Backend / Go"),
    )
    assert res.rounds
    assert res.rounds[0].criteria_snapshot, "generate должен был наполнить рубрику"


async def test_runtime_registry_is_cleaned_up():
    from app.graph import runtime

    open_run("tmp-run")
    assert "tmp-run" in runtime._REGISTRY
    close_run("tmp-run")
    assert "tmp-run" not in runtime._REGISTRY

    before = set(runtime._REGISTRY)
    await run_validation(
        cfg=ValidationConfigIn(max_rounds=1),
        statement_md=STATEMENT,
        criteria=_criteria(),
    )
    assert set(runtime._REGISTRY) == before, "run_validation должен звать close_run в finally"
