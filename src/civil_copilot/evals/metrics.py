"""Small transparent metrics used by tests, notebooks, and the evaluation runner."""

from __future__ import annotations


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
