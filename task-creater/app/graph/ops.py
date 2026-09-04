"""Чистые операции над критериями и раундами (без LLM, без графа).

Вынесены отдельно: используются и узлами графа, и сервисом применения решений
человека, и тестами. Ре-экспортируются из `app.pipeline` для обратной совместимости.
"""

from __future__ import annotations

from app.schemas import Criterion, CriterionEdit, GraderOutput, RoundArtifact, Severity

_SEV_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def apply_edits(
    criteria: list[Criterion],
    edits: list[CriterionEdit],
    accepted_ids: set[str] | None = None,
) -> list[Criterion]:
    """Новый список критериев с применёнными правками (по ключам).

    `accepted_ids=None` — применить все; иначе только правки с этими id.
    """
    by_key = {c.key: c.model_copy(deep=True) for c in criteria}
    order = [c.key for c in criteria]
    for e in edits:
        if accepted_ids is not None and e.id not in accepted_ids:
            continue
        if e.operation == "remove":
            by_key.pop(e.criterion_key, None)
            if e.criterion_key in order:
                order.remove(e.criterion_key)
        else:  # modify | add
            if e.proposed_criterion is None:
                continue
            if e.criterion_key not in by_key:
                order.append(e.criterion_key)
            by_key[e.criterion_key] = e.proposed_criterion.model_copy(deep=True)
    return [by_key[k] for k in order if k in by_key]


def _max_severity_for_key(rounds: list[RoundArtifact], key: str | None) -> Severity:
    """Максимальная severity среди находок и правок всех раундов, затрагивающих ключ."""
    best = -1
    for rd in rounds:
        for f in rd.findings:
            if f.criterion_key == key:
                best = max(best, _SEV_ORDER[f.severity])
        for e in rd.proposed_edits:
            if e.criterion_key == key:
                best = max(best, _SEV_ORDER[e.severity])
    return ("low", "medium", "high")[best] if best >= 0 else "medium"


def consolidate_edits(
    original: list[Criterion],
    recommended: list[Criterion],
    rounds: list[RoundArtifact],
) -> list[CriterionEdit]:
    """Свёртка правок всех раундов в один список ОТНОСИТЕЛЬНО исходной рубрики.

    Именно этот список показывается человеку и применяется в /decisions.
    """
    orig = {c.key: c for c in original}
    rec = {c.key: c for c in recommended}

    rationale_by_key: dict[str | None, list[str]] = {}
    addresses_by_key: dict[str | None, list[str]] = {}
    for rd in rounds:
        for e in rd.proposed_edits:
            rationale_by_key.setdefault(e.criterion_key, []).append(e.rationale)
            addresses_by_key.setdefault(e.criterion_key, []).extend(e.addresses)

    def _rationale(key: str, default: str) -> str:
        items = list(dict.fromkeys(rationale_by_key.get(key, [])))
        return " ".join(items) if items else default

    def _addresses(key: str) -> list[str]:
        return list(dict.fromkeys(addresses_by_key.get(key, [])))

    edits: list[CriterionEdit] = []
    n = 0
    for key, crit in rec.items():
        if key not in orig:
            n += 1
            edits.append(
                CriterionEdit(
                    id=f"E{n}",
                    operation="add",
                    criterion_key=key,
                    proposed_criterion=crit,
                    before_snapshot=None,
                    rationale=_rationale(key, "Добавлен по итогам валидации: аспект условия не был покрыт."),
                    addresses=_addresses(key),
                    severity=_max_severity_for_key(rounds, key),
                )
            )
        elif crit.model_dump() != orig[key].model_dump():
            n += 1
            edits.append(
                CriterionEdit(
                    id=f"E{n}",
                    operation="modify",
                    criterion_key=key,
                    proposed_criterion=crit,
                    before_snapshot=orig[key].description,
                    rationale=_rationale(key, "Формулировка уточнена по итогам валидации."),
                    addresses=_addresses(key),
                    severity=_max_severity_for_key(rounds, key),
                )
            )
    for key in orig:
        if key not in rec:
            n += 1
            edits.append(
                CriterionEdit(
                    id=f"E{n}",
                    operation="remove",
                    criterion_key=key,
                    proposed_criterion=None,
                    before_snapshot=orig[key].description,
                    rationale=_rationale(key, "Предложено убрать: дублирует другой критерий."),
                    addresses=_addresses(key),
                    severity=_max_severity_for_key(rounds, key),
                )
            )
    return edits


def build_score_samples(
    criteria: list[Criterion], gradings: list[GraderOutput]
) -> dict[str, dict[str, list[float]]]:
    """{criterion_key: {persona: [баллы по каждому сэмплу]}}.

    Одно решение могли оценить несколько раз — сэмплы нужны целиком, иначе
    разброс модели на одном и том же ответе не увидеть.
    """

    samples: dict[str, dict[str, list[float]]] = {}
    for c in criteria:
        row: dict[str, list[float]] = {}
        for g in gradings:
            for gc in g.scores:
                if gc.criterion_key == c.key:
                    row.setdefault(g.persona, []).append(round(gc.points, 2))
        samples[c.key] = row
    return samples


def build_score_matrix(
    criteria: list[Criterion], gradings: list[GraderOutput]
) -> dict[str, dict[str, float]]:
    """{criterion_key: {persona: points}} — средний балл по сэмплам этой персоны."""

    return {
        key: {persona: round(sum(values) / len(values), 2) for persona, values in row.items() if values}
        for key, row in build_score_samples(criteria, gradings).items()
    }
