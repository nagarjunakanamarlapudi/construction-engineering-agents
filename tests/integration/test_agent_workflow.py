import math

from civil_copilot.agents.router import LLMQuestionRouter
from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.data.synthetic import default_gold_scenarios, generate_demo_project
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.memory.service import InMemoryPreferenceBackend, PreferenceMemory
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.stores.qdrant import DeterministicEmbedding


def _workflow() -> CopilotWorkflow:
    corpus = generate_demo_project(seed=800)
    embedding = DeterministicEmbedding()
    vectors = {chunk.chunk_id: embedding.embed_query(chunk.text) for chunk in corpus.chunks}

    def vector_search(query: str, limit: int) -> list[tuple[str, float]]:
        query_vector = embedding.embed_query(query)
        scores = [
            (
                chunk_id,
                sum(left * right for left, right in zip(query_vector, vector, strict=True)),
            )
            for chunk_id, vector in vectors.items()
        ]
        return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]

    tools = ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, vector_search),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    return CopilotWorkflow(tools)


def test_workflow_runs_all_gold_routes_with_bounded_visible_traces_and_citations():
    workflow = _workflow()

    for scenario in default_gold_scenarios():
        response = workflow.invoke(ChatRequest(question=scenario.question))
        assert response.route == scenario.expected_route
        assert response.grounded is True
        assert response.citations
        assert len([event for event in response.trace if event.stage == "tool"]) <= 6
        assert any(event.stage == "route" for event in response.trace)
        assert any(event.stage == "plan" for event in response.trace)
        assert any(event.stage == "evidence" for event in response.trace)
        assert all(math.isfinite(item.rerank_score) for item in response.evidence)


def test_workflow_stops_safely_when_evidence_is_missing():
    corpus = generate_demo_project(seed=800)
    tools = ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, lambda _query, _limit: []),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    workflow = CopilotWorkflow(tools)

    response = workflow.invoke(
        ChatRequest(question="Explain Martian aquifer ZYXXQ-919 propulsion.")
    )

    assert response.route == "rag"
    assert response.abstained is True
    assert response.citations == []
    assert "enough evidence" in response.answer.lower()


def test_downstream_graph_question_uses_outgoing_paths_only():
    response = _workflow().invoke(ChatRequest(question="What is downstream of RFI-087?"))

    graph_event = next(event for event in response.trace if event.title == "find_graph_paths")
    assert graph_event.details["arguments"]["direction"] == "outgoing"


def test_direct_rag_exact_identifier_answer_does_not_add_unrelated_records():
    response = _workflow().invoke(ChatRequest(question="What did RFI-087 decide?"))

    assert [citation.record_id for citation in response.citations] == ["RFI-087"]


def test_workflow_applies_saved_route_preference_and_makes_memory_visible():
    workflow = _workflow()
    memory = PreferenceMemory(InMemoryPreferenceBackend())
    memory.add("reviewer", "BLR-STEEL-DEMO", "preferred_route", "graph_rag")
    workflow.memory = memory

    response = workflow.invoke(ChatRequest(question="What did RFI-087 decide?", user_id="reviewer"))

    assert response.route == "graph_rag"
    assert response.applied_preferences == {"preferred_route": "graph_rag"}
    memory_event = next(event for event in response.trace if event.stage == "memory")
    assert "1" in memory_event.summary


def test_revision_impact_answer_promotes_the_requested_schedule_activity():
    workflow = _workflow()
    workflow.router = LLMQuestionRouter(
        lambda _request: {
            "route": "agentic_rag",
            "reason": "Compare the revision and follow its impact.",
            "steps": [
                {"number": 1, "purpose": "Compare.", "tool_name": "compare_revisions"},
                {"number": 2, "purpose": "Follow.", "tool_name": "find_graph_paths"},
                {"number": 3, "purpose": "Open.", "tool_name": "get_records"},
                {"number": 4, "purpose": "Search.", "tool_name": "search_documents"},
            ],
        }
    )

    response = workflow.invoke(
        ChatRequest(
            question=(
                "What changed between S-204 Rev 3 and Rev 5, why, and what activity was affected?"
            )
        )
    )

    assert any(citation.record_id == "ACT-STEEL-009" for citation in response.citations)


def test_quality_answer_leads_with_the_open_ncr_records_that_name_failed_inspections():
    response = _workflow().invoke(
        ChatRequest(
            question=(
                "Which weld inspections raised NCRs, and which remain open pending reinspection?"
            )
        )
    )

    assert [citation.record_id for citation in response.citations[:2]] == [
        "NCR-005",
        "NCR-006",
    ]
