"""Small transparent metrics used by tests, notebooks, and the evaluation runner."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PairedRerankerNdcg:
    hybrid_ndcg: float
    reranked_ndcg: float
    lift: float


def normalized_discounted_cumulative_gain(
    retrieved: list[str],
    relevance: Mapping[str, float],
    k: int,
) -> float:
    """Return nDCG@k with duplicate results contributing no second gain."""

    if k < 1:
        raise ValueError("k must be positive")
    if any(gain < 0 for gain in relevance.values()):
        raise ValueError("relevance gains cannot be negative")

    seen: set[str] = set()
    actual_gains: list[float] = []
    for item_id in retrieved[:k]:
        gain = 0.0 if item_id in seen else float(relevance.get(item_id, 0.0))
        seen.add(item_id)
        actual_gains.append(gain)

    def dcg(gains: list[float]) -> float:
        return sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))

    ideal = dcg(sorted((float(gain) for gain in relevance.values()), reverse=True)[:k])
    if ideal == 0:
        return 1.0
    return dcg(actual_gains) / ideal


def paired_reranker_ndcg(
    hybrid_ranking: list[str],
    reranked_ranking: list[str],
    relevance: Mapping[str, float],
    k: int,
) -> PairedRerankerNdcg:
    """Compare the same fused candidates before and after second-stage reranking."""

    hybrid = normalized_discounted_cumulative_gain(hybrid_ranking, relevance, k)
    reranked = normalized_discounted_cumulative_gain(reranked_ranking, relevance, k)
    return PairedRerankerNdcg(
        hybrid_ndcg=hybrid,
        reranked_ndcg=reranked,
        lift=reranked - hybrid,
    )


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1 / rank
    return 0.0


def citation_coverage(material_claims: int, cited_claims: int) -> float:
    if material_claims == 0:
        return 1.0
    return min(cited_claims / material_claims, 1.0)


def route_accuracy(actual: str, expected: str) -> float:
    return float(actual == expected)


def tool_selection_precision(actual: list[str], expected: set[str]) -> float:
    if not actual:
        return float(not expected)
    return len(set(actual) & expected) / len(actual)


def unnecessary_step_rate(actual_steps: int, minimum_steps: int) -> float:
    if actual_steps <= 0:
        return 0.0
    return max(actual_steps - minimum_steps, 0) / actual_steps


def abstention_accuracy(expected_abstain: bool, actual_abstain: bool) -> float:
    return float(expected_abstain == actual_abstain)


def tool_selection_recall(actual: list[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(set(actual) & expected) / len(expected)


def observation_replan_success(
    actual: list[str],
    *,
    observation_index: int,
    expected_next_tool: str,
    model_turns: list[int] | None = None,
    observed_turn: int | None = None,
) -> float:
    next_index = observation_index + 1
    if model_turns is None or observed_turn is None or len(model_turns) != len(actual):
        return 0.0
    return float(
        next_index < len(actual)
        and actual[next_index] == expected_next_tool
        and model_turns[next_index] > observed_turn
    )


def repetition_rate(actual: list[str]) -> float:
    if not actual:
        return 0.0
    repeated = sum(
        1 for index, tool_name in enumerate(actual[1:], 1) if tool_name == actual[index - 1]
    )
    return repeated / len(actual)


def acl_safety(*, denied_attempts: int, leaked_source_ids: list[str]) -> float:
    if denied_attempts < 0:
        raise ValueError("denied_attempts cannot be negative")
    return float(not leaked_source_ids)


def latency_compliance(*, elapsed_ms: int, budget_ms: int) -> float:
    if elapsed_ms < 0 or budget_ms < 0:
        raise ValueError("latency values cannot be negative")
    return float(elapsed_ms <= budget_ms)


def budget_compliance(*, actual_cost_usd: float, cost_budget_usd: float) -> float:
    if actual_cost_usd < 0 or cost_budget_usd < 0:
        raise ValueError("cost values cannot be negative")
    return float(actual_cost_usd <= cost_budget_usd)
