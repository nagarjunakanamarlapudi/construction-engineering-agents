from civil_copilot.agents.router import QuestionRouter
from civil_copilot.agents.state import ChatRequest


def _route(question: str):
    return QuestionRouter().route(ChatRequest(question=question))


def test_router_selects_direct_graph_and_agentic_routes_with_bounded_plans():
    direct = _route("What did RFI-087 decide?")
    graph = _route("What is downstream of RFI-087?")
    agentic = _route(
        "Why was ACT-STEEL-009 blocked, what changed, and what evidence closes the issue?"
    )

    assert direct.route == "rag"
    assert direct.tool_names == ["search_documents"]
    assert graph.route == "graph_rag"
    assert graph.tool_names == ["find_graph_paths", "get_records"]
    assert agentic.route == "agentic_rag"
    assert {"get_schedule_activity", "find_graph_paths", "compare_revisions"} <= set(
        agentic.tool_names
    )
    assert all(len(plan.steps) <= 6 for plan in (direct, graph, agentic))


def test_explicit_route_override_is_honoured_without_adding_unsafe_tools():
    request = ChatRequest(question="Explain RFI-087", route_override="graph_rag")
    plan = QuestionRouter().route(request)

    assert plan.route == "graph_rag"
    assert "delete_records" not in plan.tool_names
