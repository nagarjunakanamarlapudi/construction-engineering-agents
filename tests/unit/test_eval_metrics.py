from civil_copilot.evals.metrics import (
    abstention_accuracy,
    citation_coverage,
    recall_at_k,
    reciprocal_rank,
    route_accuracy,
    tool_selection_precision,
    unnecessary_step_rate,
)


def test_retrieval_metrics_match_hand_calculated_examples():
    retrieved = ["A", "B", "C", "D"]
    relevant = {"B", "D", "Z"}

    assert recall_at_k(retrieved, relevant, k=3) == 1 / 3
    assert recall_at_k(retrieved, relevant, k=4) == 2 / 3
    assert reciprocal_rank(retrieved, relevant) == 1 / 2


def test_grounding_route_tool_and_efficiency_metrics_are_bounded_and_exact():
    assert citation_coverage(material_claims=4, cited_claims=3) == 0.75
    assert citation_coverage(material_claims=0, cited_claims=0) == 1.0
    assert route_accuracy("graph_rag", "graph_rag") == 1.0
    assert route_accuracy("rag", "agentic_rag") == 0.0
    assert tool_selection_precision(["search", "graph", "extra"], {"search", "graph"}) == 2 / 3
    assert unnecessary_step_rate(actual_steps=4, minimum_steps=3) == 0.25
    assert unnecessary_step_rate(actual_steps=2, minimum_steps=3) == 0.0
    assert abstention_accuracy(expected_abstain=True, actual_abstain=True) == 1.0
