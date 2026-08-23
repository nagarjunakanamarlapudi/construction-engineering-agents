from civil_copilot.agents.router import LLMQuestionRouter
from civil_copilot.agents.state import ChatRequest


def test_llm_router_accepts_bounded_allowlisted_plan_and_marks_planner():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "graph_rag",
            "reason": "The question asks for downstream relationships.",
            "steps": [
                {"number": 1, "purpose": "Follow links.", "tool_name": "find_graph_paths"},
                {"number": 2, "purpose": "Open records.", "tool_name": "get_records"},
            ],
        }
    )

    plan = router.route(ChatRequest(question="What is downstream of RFI-087?"))

    assert plan.route == "graph_rag"
    assert plan.planner == "llm"


def test_llm_router_falls_back_when_model_selects_forbidden_tool():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "agentic_rag",
            "reason": "Unsafe proposal.",
            "steps": [{"number": 1, "purpose": "Mutate data.", "tool_name": "delete_records"}],
        }
    )

    plan = router.route(ChatRequest(question="What did RFI-087 decide?"))

    assert plan.route == "rag"
    assert plan.planner == "rules"
    assert plan.tool_names == ["search_documents"]


def test_llm_router_canonicalizes_direct_rag_to_one_retrieval_tool():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "rag",
            "reason": "One focused lookup is enough.",
            "steps": [
                {"number": 1, "purpose": "Search.", "tool_name": "search_documents"},
                {"number": 2, "purpose": "Extra lookup.", "tool_name": "get_records"},
                {"number": 3, "purpose": "Unneeded quality.", "tool_name": "query_quality_records"},
            ],
        }
    )

    plan = router.route(ChatRequest(question="What did RFI-087 decide?"))

    assert plan.route == "rag"
    assert plan.planner == "llm"
    assert plan.tool_names == ["search_documents"]


def test_llm_router_removes_quality_tool_when_delay_question_has_no_quality_intent():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "agentic_rag",
            "reason": "A multi-step delay investigation is needed.",
            "steps": [
                {"number": 1, "purpose": "Schedule.", "tool_name": "get_schedule_activity"},
                {"number": 2, "purpose": "Connections.", "tool_name": "find_graph_paths"},
                {"number": 3, "purpose": "Quality.", "tool_name": "query_quality_records"},
            ],
        }
    )

    plan = router.route(ChatRequest(question="Why is ACT-STEEL-009 delayed?"))

    assert plan.route == "agentic_rag"
    assert plan.planner == "llm"
    assert plan.tool_names == ["get_schedule_activity", "find_graph_paths"]


def test_llm_router_ignores_a_final_answer_pseudo_step_but_not_unknown_actions():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "agentic_rag",
            "reason": "Investigate the activity.",
            "steps": [
                {"number": 1, "purpose": "Read schedule.", "tool_name": "get_schedule_activity"},
                {"number": 2, "purpose": "Follow links.", "tool_name": "find_graph_paths"},
                {"number": 3, "purpose": "Write answer.", "tool_name": "llm"},
            ],
        }
    )

    plan = router.route(ChatRequest(question="Why is ACT-STEEL-009 delayed?"))

    assert plan.planner == "llm"
    assert plan.tool_names == ["get_schedule_activity", "find_graph_paths"]


def test_llm_route_is_corrected_when_named_activity_delay_needs_investigation():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "graph_rag",
            "reason": "It mentions a connected record.",
            "steps": [
                {"number": 1, "purpose": "Follow links.", "tool_name": "find_graph_paths"},
                {"number": 2, "purpose": "Open records.", "tool_name": "get_records"},
            ],
        }
    )

    plan = router.route(ChatRequest(question="Why is ACT-STEEL-009 delayed?"))

    assert plan.route == "agentic_rag"
    assert plan.planner == "llm"
    assert plan.tool_names[0] == "get_schedule_activity"
    assert "guardrail" in plan.reason.lower()


def test_revision_investigation_follows_relationships_when_activity_is_requested():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "agentic_rag",
            "reason": "Compare revisions and explain the impact.",
            "steps": [
                {"number": 1, "purpose": "Compare.", "tool_name": "compare_revisions"},
                {"number": 2, "purpose": "Search.", "tool_name": "search_documents"},
            ],
        }
    )

    plan = router.route(
        ChatRequest(
            question=(
                "What changed between S-204 Rev 3 and Rev 5, why, and what activity was affected?"
            )
        )
    )

    assert plan.tool_names == [
        "compare_revisions",
        "find_graph_paths",
        "get_records",
        "search_documents",
    ]


def test_quality_investigation_uses_only_quality_graph_and_record_tools():
    router = LLMQuestionRouter(
        lambda _request: {
            "route": "agentic_rag",
            "reason": "Investigate quality closure.",
            "steps": [
                {"number": 1, "purpose": "Quality.", "tool_name": "query_quality_records"},
                {"number": 2, "purpose": "Graph.", "tool_name": "find_graph_paths"},
                {"number": 3, "purpose": "Records.", "tool_name": "get_records"},
                {"number": 4, "purpose": "Extra.", "tool_name": "search_documents"},
            ],
        }
    )

    plan = router.route(ChatRequest(question="Which NCRs remain open pending reinspection?"))

    assert plan.tool_names == [
        "query_quality_records",
        "find_graph_paths",
        "get_records",
    ]
