from pathlib import Path

from civil_copilot.agents.state import ChatRequest
from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.synthetic import default_gold_scenarios
from civil_copilot.runtime import RuntimeMode, build_application_runtime

ROOT = Path(__file__).resolve().parents[2]


def test_deterministic_portable_production_composition_covers_routes_agents_and_abstention():
    """Repeatable E2E gate over production composition; no browser, keys, or Docker."""

    corpus = load_corpus(ROOT)
    application = build_application_runtime(
        mode=RuntimeMode.PORTABLE,
        corpus=corpus,
        initialize_data=False,
    )
    try:
        published = application.ingestion.ingest(
            corpus.records,
            corpus.chunks,
            corpus.relationships,
        )
        assert published.records.created == len(corpus.records)
        assert published.chunks.created == len(corpus.chunks)
        assert published.relationships.created == len(corpus.relationships)

        scenarios = {item.scenario_id: item for item in default_gold_scenarios()}
        selected = {
            "rag": scenarios["S-01"],
            "graph_rag": scenarios["S-03"],
            "agentic_rag": scenarios["S-04"],
        }
        responses = {
            route: application.workflow.invoke(
                ChatRequest(
                    question=scenario.question,
                    conversation_id=f"portable-e2e-{route}",
                    user_id="portable-e2e-reviewer",
                    max_steps=6,
                )
            )
            for route, scenario in selected.items()
        }
        report = application.evaluator.run(list(selected.values()))
        evaluation_by_route = {item.expected_route: item for item in report.scenarios}

        assert application.capabilities.mode == RuntimeMode.PORTABLE
        assert report.runtime_capabilities["mode"] == RuntimeMode.PORTABLE
        assert set(evaluation_by_route) == set(selected)

        for route in ("rag", "graph_rag"):
            response = responses[route]
            evaluation = evaluation_by_route[route]
            assert response.route == route
            assert response.abstained is False
            assert response.grounded is True
            assert response.citations
            assert evaluation.passed is True
            assert evaluation.route_accuracy == 1.0
            assert evaluation.citation_coverage == 1.0

        assert [citation.record_id for citation in responses["graph_rag"].citations] == [
            "RFI-087",
            "ACT-STEEL-009",
            "DRAW-S-204-R5",
        ]

        agent = responses["agentic_rag"]
        agent_evaluation = evaluation_by_route["agentic_rag"]
        assert agent.route == "agentic_rag"
        assert agent.abstained is False
        assert agent.grounded is True
        assert agent.citations

        specialist_plans = {
            event.details["specialist"]
            for event in agent.trace
            if event.stage == "plan" and event.details.get("specialist")
        }
        tool_events = [event for event in agent.trace if event.stage == "tool"]
        selected_tools = {event.title for event in tool_events}
        assert specialist_plans == {"document", "schedule"}
        assert {
            "compare_revisions",
            "search_documents",
            "get_record",
            "analyze_schedule",
            "query_project_graph",
        } <= selected_tools
        assert all(event.details["specialist"] in specialist_plans for event in tool_events)

        assert agent.evaluation["citation_coverage"] == 1.0
        assert agent.evaluation["within_step_limit"] is True
        assert 1 <= agent.evaluation["tool_steps"] <= 6
        assert agent.evaluation["stop_reason"] == "completed"
        assert agent.evaluation["elapsed_ms"] >= 0
        assert agent.evaluation["estimated_cost_usd"] >= 0
        assert agent_evaluation.passed is True
        assert agent_evaluation.route_accuracy == 1.0
        assert 0.0 <= agent_evaluation.tool_selection_precision <= 1.0
        assert 0.0 <= agent_evaluation.unnecessary_step_rate <= 1.0

        abstention = application.workflow.invoke(
            ChatRequest(
                question="Explain Martian aquifer ZYXXQ-919 propulsion.",
                conversation_id="portable-e2e-abstention",
                user_id="portable-e2e-reviewer",
                access_scopes=["project:no-access"],
            )
        )
        assert abstention.route == "rag"
        assert abstention.abstained is True
        assert abstention.grounded is True
        assert abstention.citations == []
        assert "enough evidence" in abstention.answer.lower()
    finally:
        application.close()
