from __future__ import annotations

import importlib
from typing import Any

import pytest

from civil_copilot.agents.react import ReactAgentConfig, ReactRequestBudget, ReactRunResult
from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY, AgentRole
from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever


def _routing_module():
    try:
        return importlib.import_module("civil_copilot.agents.routing")
    except ModuleNotFoundError as error:
        pytest.fail(f"required specialist routing module is missing: {error.name}")


@pytest.mark.parametrize(
    ("question", "expected_role"),
    [
        ("Why is ACT-STEEL-009 delayed and which milestone is affected?", "schedule"),
        ("What changed between S-204 Rev 3 and Rev 5, and why?", "document"),
        ("Which quality NCRs remain open and why?", "risk"),
        (
            "Compare this project's structural-steel practices with the indexed IS 800 preview.",
            "document",
        ),
    ],
)
def test_compound_question_selects_the_narrow_specialist(question: str, expected_role: str):
    routing = _routing_module()

    decision = routing.SpecialistRouter().route(question)

    assert decision.mode == "specialist"
    assert decision.roles == [expected_role]
    assert decision.assignments[0].allowed_tools == sorted(
        tool.name for tool in DEFAULT_TOOL_REGISTRY.tools_for(expected_role)
    )
    assert decision.assignments[0].reason


def test_cross_discipline_revision_impact_is_a_bounded_specialist_sequence():
    routing = _routing_module()

    decision = routing.SpecialistRouter().route(
        "What changed between S-204 Rev 3 and Rev 5, and which activity was delayed?"
    )

    assert decision.mode == "specialist"
    assert decision.roles == ["document", "schedule"]
    assert len(decision.assignments) <= 2


def test_activity_identifier_counts_as_a_schedule_signal_in_a_document_question():
    routing = _routing_module()

    decision = routing.SpecialistRouter().route(
        "Why was ACT-STEEL-009 blocked, what changed, and what evidence closes the issue?"
    )

    assert decision.roles == ["document", "schedule"]


def test_ambiguous_compound_question_falls_back_to_the_general_orchestrator():
    routing = _routing_module()

    decision = routing.SpecialistRouter().route("Investigate this unusual project concern.")

    assert decision.mode == "orchestrator"
    assert decision.roles == ["orchestrator"]


def test_package_exports_the_typed_specialist_routing_contract():
    from civil_copilot import agents

    routing = _routing_module()

    assert agents.SpecialistRouter is routing.SpecialistRouter
    assert agents.SpecialistRoutingDecision is routing.SpecialistRoutingDecision
    assert agents.SpecialistAssignment is routing.SpecialistAssignment


class RecordingAgentSuite:
    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.config = ReactAgentConfig()

    def tool_names(self, role: AgentRole) -> set[str]:
        return {tool.name for tool in DEFAULT_TOOL_REGISTRY.tools_for(role)}

    def run(
        self,
        *,
        role: AgentRole,
        question: str,
        context: Any,
        callbacks: Any,
        max_steps: int,
        budget: ReactRequestBudget,
    ) -> ReactRunResult:
        self.runs.append(
            {
                "role": role,
                "question": question,
                "context": context,
                "callbacks": callbacks,
                "max_steps": max_steps,
                "budget": budget,
            }
        )
        return ReactRunResult(
            role=role,
            answer="Completed from permitted evidence.",
            tool_names=[],
            observations=[],
            source_ids=[],
            trace=[],
            stop_reason="completed",
            abstained=False,
            thread_id=f"specialist-{role}",
        )


class IncompleteSecondSpecialistSuite(RecordingAgentSuite):
    def run(self, **kwargs: Any) -> ReactRunResult:
        result = super().run(**kwargs)
        if kwargs["role"] == "schedule":
            return result.model_copy(
                update={
                    "answer": "The investigation reached its step limit.",
                    "stop_reason": "step_limit",
                    "abstained": True,
                }
            )
        return result


def _workflow(suite: RecordingAgentSuite) -> CopilotWorkflow:
    corpus = generate_demo_project(seed=800)
    tools = ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, lambda _query, _limit: []),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    return CopilotWorkflow(tools, react_agents=suite)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("question", "expected_role", "expected_tools"),
    [
        (
            "Why is ACT-STEEL-009 delayed and which milestone is affected?",
            "schedule",
            ["analyze_schedule", "calculate", "get_record", "query_project_graph"],
        ),
        (
            "What changed between S-204 Rev 3 and Rev 5, and why?",
            "document",
            [
                "assess_standard_evidence",
                "compare_revisions",
                "get_record",
                "search_documents",
            ],
        ),
        (
            "Which quality NCRs remain open and why?",
            "risk",
            [
                "analyze_schedule",
                "assess_standard_evidence",
                "calculate",
                "get_record",
                "query_project_graph",
                "search_documents",
            ],
        ),
    ],
)
def test_workflow_invokes_expected_specialist_and_exposes_its_allowlist(
    question: str,
    expected_role: AgentRole,
    expected_tools: list[str],
):
    suite = RecordingAgentSuite()

    response = _workflow(suite).invoke(ChatRequest(question=question, route_override="agentic_rag"))

    assert [run["role"] for run in suite.runs] == [expected_role]
    delegation = next(
        event for event in response.trace if event.details.get("specialist") == expected_role
    )
    assert delegation.stage == "plan"
    assert delegation.details["allowed_tools"] == expected_tools
    assert delegation.details["sequence_index"] == 1
    assert delegation.details["sequence_size"] == 1


def test_direct_rag_never_invokes_a_specialist_agent():
    suite = RecordingAgentSuite()

    response = _workflow(suite).invoke(ChatRequest(question="What did RFI-087 decide?"))

    assert response.route == "rag"
    assert suite.runs == []
    assert not any(event.details.get("specialist") for event in response.trace)


def test_required_specialist_sequence_does_not_publish_when_one_role_is_incomplete():
    suite = IncompleteSecondSpecialistSuite()

    response = _workflow(suite).invoke(
        ChatRequest(
            question=(
                "What changed between S-204 Rev 3 and Rev 5, and which activity was delayed?"
            ),
            route_override="agentic_rag",
        )
    )

    assert [run["role"] for run in suite.runs] == ["document", "schedule"]
    assert response.abstained is True
    assert response.evaluation["stop_reason"] == "step_limit"
