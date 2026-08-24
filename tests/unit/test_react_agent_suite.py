import importlib
import json
import multiprocessing
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from langchain.tools import ToolRuntime, tool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool

from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.tool_contracts import CalculateInput, ReadOnlyToolObservation
from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY, ToolRegistry
from civil_copilot.agents.tool_runtime import AgentToolContext
from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.application_tools import StoreBackedProjectTools
from civil_copilot.calculation.service import CalculationService
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.schedule.service import ScheduleImpactService


def _react_module():
    try:
        return importlib.import_module("civil_copilot.agents.react")
    except ModuleNotFoundError as error:
        pytest.fail(f"required Task 2 module is missing: {error.name}")


def _context() -> AgentToolContext:
    corpus = generate_demo_project(seed=800)

    def vector_search(_query: str, limit: int) -> list[tuple[str, float]]:
        return [(chunk.chunk_id, 0.5) for chunk in corpus.chunks[:limit]]

    project_tools = ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, vector_search),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    return AgentToolContext(
        user_id="reviewer",
        project_id="BLR-STEEL-DEMO",
        access_scopes=("project:blr-steel-demo",),
        project_tools=project_tools,
        schedule_service=ScheduleImpactService(corpus.records),
        calculation_service=CalculationService(),
        request_id="thread-observation-driven",
    )


class ObservationDrivenModel(BaseChatModel):
    """Choose the second action from the first real tool observation."""

    @property
    def _llm_type(self) -> str:
        return "observation-driven-test-model"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        if not tool_messages:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "analyze_schedule",
                        "args": {
                            "activity_ids": ["ACT-STEEL-009"],
                            "delay_days": 5,
                            "as_of_date": None,
                        },
                        "id": "schedule-call",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            observation = json.loads(str(tool_messages[-1].content))
            if (
                tool_messages[-1].name == "analyze_schedule"
                and observation["data"]["projected_critical_delay_days"] > 0
            ):
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "query_project_graph",
                            "args": {
                                "start_id": "ACT-STEEL-009",
                                "relationship_types": ["AFFECTS", "BLOCKS"],
                                "max_depth": 2,
                                "direction": "both",
                            },
                            "id": "graph-call",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                message = AIMessage(content="Investigation complete from permitted evidence.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class AgentInvocationFailureModel(ObservationDrivenModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError("sensitive provider failure details")


class RepeatAfterSuccessfulSearchModel(ObservationDrivenModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        call_number = sum(isinstance(message, ToolMessage) for message in messages) + 1
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_documents",
                                "args": {
                                    "query": "S-204 ACT-STEEL-009 blocked",
                                    "filters": {},
                                    "top_k": 6,
                                },
                                "id": f"repeated-search-{call_number}",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class LoopingCalculationModel(ObservationDrivenModel):
    @property
    def _llm_type(self) -> str:
        return "looping-calculation-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        call_number = len([message for message in messages if isinstance(message, ToolMessage)]) + 1
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "calculate",
                    "args": {"expression": "1 + 1"},
                    "id": f"calculation-{call_number}",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class CostlyToolModel(ObservationDrivenModel):
    @property
    def _llm_type(self) -> str:
        return "costly-tool-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "calculate",
                    "args": {"expression": "40 + 2"},
                    "id": "over-budget-call",
                    "type": "tool_call",
                }
            ],
            usage_metadata={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class SlowFinalModel(ObservationDrivenModel):
    @property
    def _llm_type(self) -> str:
        return "slow-final-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        time.sleep(0.005)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Done."))])


class SafeStopModel(ObservationDrivenModel):
    stop_reason: ClassVar[str] = "clarification"

    @property
    def _llm_type(self) -> str:
        return "safe-stop-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=(
                            f"STOP_REASON:{self.stop_reason}\n"
                            "Please identify the activity or controlled record."
                        )
                    )
                )
            ]
        )


class RecordReadingModel(ObservationDrivenModel):
    @property
    def _llm_type(self) -> str:
        return "record-reading-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        if isinstance(messages[-1], HumanMessage):
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_record",
                        "args": {
                            "record_type": "schedule_activity",
                            "record_id": "ACT-STEEL-009",
                            "as_of_date": None,
                        },
                        "id": "record-call",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="I cannot ground a permitted answer.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class MultiCallModel(ObservationDrivenModel):
    """Adversarially proposes action two before observing action one."""

    @property
    def _llm_type(self) -> str:
        return "multi-call-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        if not tool_messages:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "analyze_schedule",
                        "args": {
                            "activity_ids": ["ACT-STEEL-009"],
                            "delay_days": 5,
                            "as_of_date": None,
                        },
                        "id": "parallel-schedule",
                        "type": "tool_call",
                    },
                    {
                        "name": "query_project_graph",
                        "args": {
                            "start_id": "ACT-STEEL-009",
                            "relationship_types": ["AFFECTS", "BLOCKS"],
                            "max_depth": 2,
                            "direction": "both",
                        },
                        "id": "premature-graph",
                        "type": "tool_call",
                    },
                ],
            )
        elif tool_messages[-1].name == "analyze_schedule":
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_project_graph",
                        "args": {
                            "start_id": "ACT-STEEL-009",
                            "relationship_types": ["AFFECTS", "BLOCKS"],
                            "max_depth": 2,
                            "direction": "both",
                        },
                        "id": "observed-graph",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="Completed after sequential observations.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class EvidenceThenStopModel(RecordReadingModel):
    stop_reason: ClassVar[str] = "human_review"

    @property
    def _llm_type(self) -> str:
        return "evidence-then-stop-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        if not any(isinstance(message, ToolMessage) for message in messages):
            return super()._generate(messages, **kwargs)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=f"STOP_REASON:{self.stop_reason}\nManual review required."
                    )
                )
            ]
        )


class SearchThenFinalModel(ObservationDrivenModel):
    as_of_date: ClassVar[str | None] = None

    @property
    def _llm_type(self) -> str:
        return "search-then-final-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        if not any(isinstance(message, ToolMessage) for message in messages):
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_documents",
                        "args": {
                            "query": "S-204 framing revision",
                            "filters": {"as_of_date": self.as_of_date},
                            "top_k": 20,
                        },
                        "id": "search-call",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="Search complete.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class ErrorThenFinalModel(LoopingCalculationModel):
    @property
    def _llm_type(self) -> str:
        return "error-then-final-test-model"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        if any(isinstance(message, ToolMessage) for message in messages):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Done."))])
        return super()._generate(messages, **kwargs)


@tool(
    "calculate",
    args_schema=CalculateInput,
    description=DEFAULT_TOOL_REGISTRY.get("calculate").description,
)
def transient_calculator(
    expression: str,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    raise ConnectionError("private database host leaked")


def _registry_with_transient_calculator() -> ToolRegistry:
    specifications = [DEFAULT_TOOL_REGISTRY.get(name) for name in DEFAULT_TOOL_REGISTRY.names()]
    return ToolRegistry(
        [
            replace(
                specification,
                tool=transient_calculator,
                description=transient_calculator.description,
                input_schema=CalculateInput,
            )
            if specification.name == "calculate"
            else specification
            for specification in specifications
        ]
    )


def _context_with_temporal_chunks() -> AgentToolContext:
    corpus = generate_demo_project(seed=800)
    dates = {record.record_id: record.effective_date for record in corpus.records}
    chunks = [
        chunk.model_copy(update={"effective_date": dates.get(chunk.record_id)})
        for chunk in corpus.chunks
    ]

    def vector_search(_query: str, limit: int) -> list[tuple[str, float]]:
        return [(chunk.chunk_id, 0.5) for chunk in chunks[:limit]]

    project_tools = ProjectTools(
        corpus.records,
        HybridRetriever(chunks, vector_search),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    return AgentToolContext(
        user_id="temporal-reviewer",
        project_id="BLR-STEEL-DEMO",
        access_scopes=("project:blr-steel-demo",),
        project_tools=project_tools,
        schedule_service=ScheduleImpactService(corpus.records),
        calculation_service=CalculationService(),
        request_id="temporal-thread",
    )


def test_specialists_receive_only_registry_tools_for_their_bounded_role():
    react = _react_module()
    suite = react.ReactAgentSuite(ObservationDrivenModel())

    assert suite.tool_names("document") == {
        "search_documents",
        "get_record",
        "compare_revisions",
        "assess_standard_evidence",
    }
    assert suite.tool_names("schedule") == {
        "get_record",
        "query_project_graph",
        "analyze_schedule",
        "calculate",
    }
    assert suite.tool_names("risk") == {
        "search_documents",
        "get_record",
        "query_project_graph",
        "analyze_schedule",
        "calculate",
        "assess_standard_evidence",
    }
    assert suite.tool_names("orchestrator") == {
        "search_documents",
        "get_record",
        "query_project_graph",
        "analyze_schedule",
        "compare_revisions",
        "calculate",
        "assess_standard_evidence",
    }


def test_package_exports_stable_suite_config_context_and_registry_api():
    from civil_copilot import agents
    from civil_copilot.agents import tool_runtime

    assert agents.ReactAgentSuite is _react_module().ReactAgentSuite
    assert agents.ReactAgentConfig is _react_module().ReactAgentConfig
    assert agents.AgentToolContext is AgentToolContext
    assert agents.SignalToolDeadlineRunner is tool_runtime.SignalToolDeadlineRunner
    assert agents.ToolDeadlineExceeded is tool_runtime.ToolDeadlineExceeded
    assert agents.ToolDeadlineUnavailable is tool_runtime.ToolDeadlineUnavailable
    assert agents.DEFAULT_TOOL_REGISTRY.names()


def test_create_agent_replans_after_observation_and_checkpoints_the_tool_messages():
    react = _react_module()
    suite = react.ReactAgentSuite(ObservationDrivenModel())
    context = _context()

    result = suite.run(
        role="orchestrator",
        question="Why is ACT-STEEL-009 delayed and what is affected?",
        context=context,
    )

    assert result.tool_names == ["analyze_schedule", "query_project_graph"]
    assert result.stop_reason == "completed"
    assert "ACT-STEEL-009" in result.source_ids
    assert [event.phase for event in result.trace] == [
        "plan",
        "act",
        "observe",
        "decide",
        "act",
        "observe",
        "decide",
    ]
    assert [event.model_turn for event in result.trace] == [0, 1, 1, 2, 2, 2, 3]
    schedule_act = next(
        event
        for event in result.trace
        if event.phase == "act" and event.tool_name == "analyze_schedule"
    )
    assert schedule_act.tool_metadata["acl_policy"] == "schedule:read"
    assert schedule_act.tool_metadata["owning_specialist"] == "schedule"
    checkpoint = suite.checkpoint("orchestrator", context)
    assert checkpoint is not None
    assert any(isinstance(message, ToolMessage) for message in checkpoint.values["messages"])


def test_parallel_model_tool_calls_are_truncated_until_the_first_observation_is_seen():
    react = _react_module()

    result = react.ReactAgentSuite(MultiCallModel()).run(
        role="orchestrator",
        question="Assess schedule and downstream effects.",
        context=_context(),
    )

    assert result.tool_names == ["analyze_schedule", "query_project_graph"]
    assert [event.phase for event in result.trace] == [
        "plan",
        "safety",
        "act",
        "observe",
        "decide",
        "act",
        "observe",
        "decide",
    ]
    first_observe = next(
        event for event in result.trace if event.phase == "observe" and event.model_turn == 1
    )
    second_act = next(
        event
        for event in result.trace
        if event.phase == "act" and event.tool_name == "query_project_graph"
    )
    assert second_act.model_turn > first_observe.model_turn
    assert second_act.tool_call_id == "observed-graph"


def test_checkpoint_identity_is_canonical_non_empty_and_isolated_by_user():
    react = _react_module()
    suite = react.ReactAgentSuite(RecordReadingModel())
    base = _context()
    owner = replace(
        base,
        user_id="owner",
        request_id="owner-request",
        conversation_id="shared-conversation",
    )
    intruder = replace(
        base,
        user_id="intruder",
        access_scopes=("public",),
        request_id="intruder-request",
        conversation_id="shared-conversation",
    )

    owner_result = suite.run(role="document", question="Open the activity.", context=owner)
    intruder_result = suite.run(role="document", question="Open the activity.", context=intruder)

    assert owner_result.thread_id == (
        "project=BLR-STEEL-DEMO|user=owner|role=document|"
        "conversation=shared-conversation|acl=dbbf93e70e160f3e"
    )
    assert intruder_result.thread_id != owner_result.thread_id
    assert owner_result.source_ids == ["ACT-STEEL-009"]
    assert intruder_result.source_ids == []
    assert (
        suite.checkpoint("document", owner).values["messages"]
        != suite.checkpoint("document", intruder).values["messages"]
    )
    with pytest.raises(ValueError, match="request_id"):
        replace(base, request_id="")


def test_per_request_step_budget_ignores_prior_turns_in_the_same_checkpoint():
    react = _react_module()
    suite = react.ReactAgentSuite(RecordReadingModel())
    context = replace(_context(), request_id="continued-thread")

    first = suite.run(role="document", question="Open once.", context=context, max_steps=1)
    second = suite.run(role="document", question="Open again.", context=context, max_steps=1)

    assert first.tool_names == ["get_record"]
    assert second.tool_names == ["get_record"]


def test_middleware_stops_a_repeating_agent_at_the_shared_tool_budget():
    react = _react_module()
    suite = react.ReactAgentSuite(
        LoopingCalculationModel(),
        config=react.ReactAgentConfig(
            max_model_calls=4,
            max_tool_calls=2,
            max_repeated_tool_calls=2,
        ),
    )

    result = suite.run(
        role="schedule",
        question="Keep calculating forever.",
        context=_context(),
    )

    assert result.tool_names == ["calculate", "calculate"]
    assert result.stop_reason == "step_limit"
    assert result.abstained is True


def test_model_call_limit_is_never_reported_as_completed():
    react = _react_module()
    result = react.ReactAgentSuite(
        LoopingCalculationModel(),
        config=react.ReactAgentConfig(
            max_model_calls=2,
            max_tool_calls=6,
            max_repeated_tool_calls=2,
        ),
    ).run(role="schedule", question="Loop.", context=_context())

    assert result.stop_reason == "step_limit"
    assert result.abstained is True
    assert "model call limit" not in result.answer.lower()


def test_repetition_guard_stops_before_a_third_identical_tool_execution():
    react = _react_module()
    suite = react.ReactAgentSuite(
        LoopingCalculationModel(),
        config=react.ReactAgentConfig(
            max_model_calls=8,
            max_tool_calls=6,
            max_repeated_tool_calls=2,
        ),
    )

    result = suite.run(
        role="schedule",
        question="Keep repeating the same calculation.",
        context=_context(),
    )

    assert result.tool_names == ["calculate", "calculate"]
    assert result.stop_reason == "repetition"
    assert result.abstained is True


def test_default_repetition_guard_blocks_second_identical_call_after_success():
    react = _react_module()
    result = react.ReactAgentSuite(RepeatAfterSuccessfulSearchModel()).run(
        role="document",
        question="Find the S-204 evidence once.",
        context=_context(),
    )

    assert result.tool_names == ["search_documents"]
    assert result.observations[0].status == "ok"
    assert result.stop_reason == "repetition"


def test_agent_can_answer_after_using_its_last_permitted_tool_step():
    react = _react_module()
    result = react.ReactAgentSuite(SearchThenFinalModel()).run(
        role="document",
        question="What S-204 evidence is available?",
        context=_context(),
        max_steps=1,
    )

    assert result.tool_names == ["search_documents"]
    assert result.source_ids
    assert result.stop_reason == "completed"
    assert result.abstained is False


def test_cost_and_wall_clock_budgets_short_circuit_before_an_action():
    react = _react_module()
    costly = react.ReactAgentSuite(
        CostlyToolModel(),
        config=react.ReactAgentConfig(
            max_cost_usd=0.01,
            input_cost_per_1k_tokens=1.0,
            output_cost_per_1k_tokens=1.0,
        ),
    ).run(role="schedule", question="Calculate it.", context=_context())
    slow = react.ReactAgentSuite(
        SlowFinalModel(),
        config=react.ReactAgentConfig(max_seconds=0.001),
    ).run(role="schedule", question="Assess it.", context=_context())

    assert costly.stop_reason == "cost_limit"
    assert costly.observations == []
    assert costly.estimated_cost_usd >= 0.01
    assert slow.stop_reason == "time_limit"
    assert slow.elapsed_ms >= 1


@pytest.mark.parametrize("reason", ["clarification", "abstained", "human_review"])
def test_structured_safe_stop_reasons_are_preserved_without_control_prefix(reason: str):
    react = _react_module()
    SafeStopModel.stop_reason = reason

    result = react.ReactAgentSuite(SafeStopModel()).run(
        role="orchestrator",
        question="Investigate the ambiguous request.",
        context=_context(),
    )

    assert result.stop_reason == reason
    assert result.abstained is True
    assert "STOP_REASON" not in result.answer


def test_acl_denial_is_a_redacted_observation_and_never_a_completed_answer():
    react = _react_module()
    context = _context()
    denied_context = AgentToolContext(
        user_id=context.user_id,
        project_id=context.project_id,
        access_scopes=("public",),
        project_tools=context.project_tools,
        schedule_service=context.schedule_service,
        calculation_service=context.calculation_service,
        request_id="denied-thread",
    )

    result = react.ReactAgentSuite(RecordReadingModel()).run(
        role="document",
        question="Open ACT-STEEL-009.",
        context=denied_context,
    )

    assert result.stop_reason == "abstained"
    assert result.source_ids == []
    assert result.observations[0].status == "denied"
    assert "outside the permitted project scope" in result.observations[0].summary
    assert "project:blr-steel-demo" not in result.model_dump_json()


def test_v2_stream_contains_state_updates_and_safe_custom_tool_progress():
    react = _react_module()
    suite = react.ReactAgentSuite(ObservationDrivenModel())

    chunks = list(
        suite.stream(
            role="schedule",
            question="Assess ACT-STEEL-009.",
            context=_context(),
        )
    )

    assert {chunk["type"] for chunk in chunks} >= {"updates", "custom"}
    custom = [chunk["data"] for chunk in chunks if chunk["type"] == "custom"]
    assert any(event["phase"] == "tool_started" for event in custom)
    assert all("content" not in event for event in custom)


def test_search_and_graph_observations_preserve_bounded_typed_evidence():
    react = _react_module()
    search = react.ReactAgentSuite(SearchThenFinalModel()).run(
        role="document",
        question="Find S-204 evidence.",
        context=_context(),
    )
    graph = react.ReactAgentSuite(ObservationDrivenModel()).run(
        role="orchestrator",
        question="Assess ACT-STEEL-009 impacts.",
        context=_context(),
    )

    assert search.observations[0].evidence
    assert search.observations[0].citations
    assert max(len(item.chunk.text) for item in search.observations[0].evidence) <= 1200
    assert graph.observations[1].graph_paths
    assert graph.observations[1].graph_paths[0].edges


def test_registry_tool_timeout_returns_a_structured_error_within_the_budget_envelope():
    from civil_copilot.agents.guardrails import RegistryToolBudgetMiddleware

    specification = replace(DEFAULT_TOOL_REGISTRY.get("calculate"), time_budget_seconds=0.02)
    middleware = RegistryToolBudgetMiddleware(ToolRegistry([specification]))
    request = SimpleNamespace(tool_call={"name": "calculate", "id": "slow-call"})

    def slow_handler(_request):
        time.sleep(0.2)
        return ToolMessage(content="late", tool_call_id="slow-call", name="calculate")

    started = time.monotonic()
    message = middleware.wrap_tool_call(request, slow_handler)
    elapsed = time.monotonic() - started
    observation = ReadOnlyToolObservation.model_validate_json(message.content)

    assert elapsed < 0.1
    assert observation.tool_name == "calculate"
    assert observation.status == "error"
    assert observation.errors[0].code == "tool_time_limit"


def test_synchronous_timeout_terminates_handler_before_post_budget_mutation():
    from civil_copilot.agents.guardrails import RegistryToolBudgetMiddleware

    specification = replace(DEFAULT_TOOL_REGISTRY.get("calculate"), time_budget_seconds=0.02)
    middleware = RegistryToolBudgetMiddleware(ToolRegistry([specification]))
    request = SimpleNamespace(tool_call={"name": "calculate", "id": "mutation-call"})
    post_budget_mutations: list[str] = []

    def mutating_handler(_request):
        time.sleep(0.15)
        post_budget_mutations.append("mutated")
        return ToolMessage(content="late", tool_call_id="mutation-call", name="calculate")

    message = middleware.wrap_tool_call(request, mutating_handler)
    time.sleep(0.2)
    observation = ReadOnlyToolObservation.model_validate_json(message.content)

    assert observation.status == "error"
    assert observation.errors[0].code == "tool_time_limit"
    assert post_budget_mutations == []


def test_context_backed_project_tools_timeout_interrupts_before_late_mutation():
    from civil_copilot.agents.guardrails import RegistryToolBudgetMiddleware

    specification = replace(DEFAULT_TOOL_REGISTRY.get("calculate"), time_budget_seconds=0.02)
    middleware = RegistryToolBudgetMiddleware(ToolRegistry([specification]))
    request = SimpleNamespace(
        tool_call={"name": "calculate", "id": "context-mutation-call"},
        runtime=SimpleNamespace(context=_context()),
    )
    post_budget_mutations: list[str] = []

    def mutating_handler(_request):
        time.sleep(0.15)
        post_budget_mutations.append("mutated")
        return ToolMessage(
            content="late",
            tool_call_id="context-mutation-call",
            name="calculate",
        )

    started = time.monotonic()
    message = middleware.wrap_tool_call(request, mutating_handler)
    elapsed = time.monotonic() - started
    time.sleep(0.2)
    observation = ReadOnlyToolObservation.model_validate_json(message.content)

    assert elapsed < 0.1
    assert observation.errors[0].code == "tool_time_limit"
    assert post_budget_mutations == []


def test_signal_deadline_runner_interrupts_before_mutation():
    from civil_copilot.agents.tool_runtime import (
        SignalToolDeadlineRunner,
        ToolDeadlineExceeded,
    )

    post_budget_mutations: list[str] = []

    def operation():
        time.sleep(0.15)
        post_budget_mutations.append("mutated")

    started = time.monotonic()
    with pytest.raises(ToolDeadlineExceeded):
        SignalToolDeadlineRunner().run(
            operation,
            tool_name="calculate",
            timeout_seconds=0.02,
        )
    elapsed = time.monotonic() - started
    time.sleep(0.2)

    assert elapsed < 0.1
    assert post_budget_mutations == []


def test_unverified_dependency_runner_fails_closed_before_operation_starts():
    from civil_copilot.agents.guardrails import RegistryToolBudgetMiddleware

    class PostHocRunner:
        def run(self, operation, *, tool_name: str, timeout_seconds: float):
            return operation()

    specification = replace(DEFAULT_TOOL_REGISTRY.get("calculate"), time_budget_seconds=0.02)
    middleware = RegistryToolBudgetMiddleware(ToolRegistry([specification]))
    context = replace(_context(), tool_deadline_runner=PostHocRunner())
    request = SimpleNamespace(
        tool_call={"name": "calculate", "id": "unverified-runner-call"},
        runtime=SimpleNamespace(context=context),
    )
    mutations: list[str] = []

    def mutating_handler(_request):
        mutations.append("started")
        return ToolMessage(
            content="unverified",
            tool_call_id="unverified-runner-call",
            name="calculate",
        )

    message = middleware.wrap_tool_call(request, mutating_handler)
    observation = ReadOnlyToolObservation.model_validate_json(message.content)

    assert observation.errors[0].code == "tool_deadline_unavailable"
    assert mutations == []


def test_store_backed_context_uses_native_deadline_without_copying_live_clients():
    corpus = generate_demo_project(seed=800)

    class NonPickleableReaders:
        def __init__(self):
            self.lock = threading.Lock()
            self.execution_pid: int | None = None

        def query_records(self, **kwargs):
            self.execution_pid = os.getpid()
            record_ids = set(kwargs.get("record_ids") or [])
            return [
                record
                for record in corpus.records
                if (not record_ids or record.record_id in record_ids)
                and record.project_id == kwargs["project_id"]
            ][: kwargs.get("limit", 100)]

        def search_hybrid(self, **_kwargs):
            return []

        def find_paths(self, *_args, **_kwargs):
            return []

    readers = NonPickleableReaders()
    project_tools = StoreBackedProjectTools(
        readers,
        readers,
        readers,
        default_project_id="BLR-STEEL-DEMO",
        default_access_scopes=("project:blr-steel-demo",),
    )
    context = AgentToolContext(
        user_id="store-reviewer",
        project_id="BLR-STEEL-DEMO",
        access_scopes=("project:blr-steel-demo",),
        project_tools=project_tools,
        schedule_service=ScheduleImpactService(corpus.records),
        calculation_service=CalculationService(),
        request_id="store-context-deadline",
    )

    result = (
        _react_module()
        .ReactAgentSuite(RecordReadingModel())
        .run(
            role="document",
            question="Open ACT-STEEL-009.",
            context=context,
        )
    )

    assert result.stop_reason == "completed"
    assert result.source_ids == ["ACT-STEEL-009"]
    assert readers.execution_pid == os.getpid()


def test_headless_react_execution_does_not_spawn_child_processes(monkeypatch):
    def reject_child_processes(*_args, **_kwargs):
        raise AssertionError("ReAct execution attempted to create a child process")

    monkeypatch.setattr(multiprocessing, "get_context", reject_child_processes)
    started = time.monotonic()

    result = (
        _react_module()
        .ReactAgentSuite(RecordReadingModel())
        .run(
            role="document",
            question="Open ACT-STEEL-009.",
            context=_context(),
        )
    )

    assert result.stop_reason == "completed"
    assert result.source_ids == ["ACT-STEEL-009"]
    assert time.monotonic() - started < 2.0


def test_tool_raised_timeout_is_preserved_for_retry_middleware():
    from civil_copilot.agents.guardrails import RegistryToolBudgetMiddleware

    specification = replace(DEFAULT_TOOL_REGISTRY.get("calculate"), time_budget_seconds=0.1)
    middleware = RegistryToolBudgetMiddleware(ToolRegistry([specification]))
    request = SimpleNamespace(tool_call={"name": "calculate", "id": "timeout-call"})

    def transient_timeout(_request):
        raise TimeoutError("upstream timeout")

    with pytest.raises(TimeoutError, match="upstream timeout"):
        middleware.wrap_tool_call(request, transient_timeout)


def test_reranked_search_has_one_hard_attempt_without_middleware_retry(monkeypatch):
    attempts: list[str] = []

    def transient_search(_self, request):
        attempts.append(request.tool_name)
        raise TimeoutError("bounded search dependency timeout")

    monkeypatch.setattr(ProjectTools, "call", transient_search)

    result = (
        _react_module()
        .ReactAgentSuite(SearchThenFinalModel())
        .run(
            role="document",
            question="Search the current controlled revision.",
            context=_context(),
        )
    )

    assert attempts == ["search_documents"]
    assert result.stop_reason == "error"


def test_retry_exhaustion_returns_redacted_structured_tool_error():
    react = _react_module()
    result = react.ReactAgentSuite(
        ErrorThenFinalModel(), registry=_registry_with_transient_calculator()
    ).run(role="schedule", question="Calculate safely.", context=_context())

    assert result.stop_reason == "error"
    assert result.answer == "A read-only evidence tool failed, so no answer was published."
    assert result.tool_names == ["calculate"]
    assert result.observations[0].status == "error"
    assert result.observations[0].errors[0].code == "transient_failure"
    assert "private database host" not in result.model_dump_json()


def test_unexpected_tool_failure_is_structured_and_redacted():
    react = _react_module()
    request = SimpleNamespace(tool_call={"name": "calculate", "id": "unexpected"})

    def fail_unexpectedly(_request):
        raise RuntimeError("private implementation detail")

    message = react.redact_expected_tool_errors.wrap_tool_call(request, fail_unexpectedly)
    observation = ReadOnlyToolObservation.model_validate_json(message.content)

    assert observation.tool_name == "calculate"
    assert observation.status == "error"
    assert observation.errors[0].code == "unexpected_tool_failure"
    assert "private implementation detail" not in message.content


def test_model_visible_as_of_date_filters_search_and_schedule_snapshots():
    react = _react_module()
    SearchThenFinalModel.as_of_date = "2026-02-10"
    search = react.ReactAgentSuite(SearchThenFinalModel()).run(
        role="document",
        question="What S-204 revision was effective?",
        context=_context_with_temporal_chunks(),
    )
    schedule = _context().schedule_service

    assert "DRAW-S-204-R3" in search.source_ids
    assert "DRAW-S-204-R5" not in search.source_ids
    with pytest.raises(ValueError, match="not effective"):
        schedule.analyze(["ACT-STEEL-009"], delay_days=2, as_of_date=date(2026, 2, 17))
    current = schedule.analyze(["ACT-STEEL-009"], delay_days=2, as_of_date=date(2026, 2, 18))
    assert current.as_of_date == date(2026, 2, 18)


def test_copilot_workflow_uses_react_observations_for_compound_route_only():
    react = _react_module()
    context = _context()
    workflow = CopilotWorkflow(
        context.project_tools,
        react_agents=react.ReactAgentSuite(ObservationDrivenModel()),
    )

    response = workflow.invoke(
        ChatRequest(
            question="Why is ACT-STEEL-009 delayed and what is affected?",
            user_id="reviewer",
            route_override="agentic_rag",
        )
    )

    react_tools = [
        event.title
        for event in response.trace
        if event.stage == "tool" and event.title in {"analyze_schedule", "query_project_graph"}
    ]
    assert react_tools == ["analyze_schedule", "query_project_graph"]
    assert response.route == "agentic_rag"
    assert response.grounded is True
    assert any(citation.record_id == "ACT-STEEL-009" for citation in response.citations)
    assert response.evaluation["stop_reason"] == "completed"
    assert int(response.evaluation["elapsed_ms"]) >= 0
    assert float(response.evaluation["estimated_cost_usd"]) >= 0
    stages = [event.stage for event in response.trace]
    assert "act" in stages
    assert "observe" in stages
    assert "decide" in stages
    schedule_trace = next(
        event
        for event in response.trace
        if event.stage == "act" and event.title == "Call analyze_schedule"
    )
    assert schedule_trace.details["tool_metadata"]["time_budget_seconds"] == 12.0
    assert response.graph_paths


def test_workflow_converts_agent_invocation_exception_to_safe_control_stop():
    react = _react_module()
    context = _context()
    response = CopilotWorkflow(
        context.project_tools,
        react_agents=react.ReactAgentSuite(AgentInvocationFailureModel()),
    ).invoke(
        ChatRequest(
            question=(
                "Why was ACT-STEEL-009 blocked, what changed in S-204, "
                "and what activity was affected?"
            ),
            route_override="agentic_rag",
        )
    )

    assert response.route == "agentic_rag"
    assert response.grounded is False
    assert response.abstained is True
    assert response.citations == []
    assert response.answer == ("The agent investigation failed safely, so no answer was published.")
    assert response.evaluation["stop_reason"] == "agent_error"
    assert response.evaluation["review_required"] is False
    assert "sensitive provider failure details" not in response.model_dump_json()
    safety = next(
        event
        for event in response.trace
        if event.stage == "safety" and event.details.get("stop_reason") == "agent_error"
    )
    assert safety.details["error_type"] == "RuntimeError"
    assert safety.details["specialist"] == "document"


@pytest.mark.parametrize(
    "reason",
    [
        "human_review",
        "clarification",
        "step_limit",
        "time_limit",
        "cost_limit",
        "repetition",
        "error",
        "abstained",
    ],
)
def test_workflow_never_publishes_a_normal_answer_after_non_completed_stop(reason: str):
    react = _react_module()
    EvidenceThenStopModel.stop_reason = reason
    context = _context()
    workflow = CopilotWorkflow(
        context.project_tools,
        react_agents=react.ReactAgentSuite(EvidenceThenStopModel()),
    )

    response = workflow.invoke(
        ChatRequest(
            question="Open ACT-STEEL-009 and decide.",
            user_id="reviewer",
            route_override="agentic_rag",
        )
    )

    assert response.evaluation["stop_reason"] == reason
    assert response.evaluation["review_required"] is (reason == "human_review")
    expected_messages = {
        "human_review": (
            "This investigation requires human review before an answer can be published."
        ),
        "clarification": (
            "More project detail is required before this investigation can continue safely."
        ),
        "step_limit": "The investigation reached its step limit without a publishable answer.",
        "time_limit": "The investigation reached its time limit without a publishable answer.",
        "cost_limit": "The investigation reached its cost limit without a publishable answer.",
        "repetition": (
            "The investigation stopped after repeated actions produced no safe resolution."
        ),
        "error": "A read-only evidence tool failed, so no answer was published.",
        "abstained": "Permitted project evidence was insufficient to publish an answer.",
    }
    assert response.answer == expected_messages[reason]
    assert response.grounded is False
    assert response.abstained is True
    assert response.citations == []


def test_workflow_replaces_normal_model_text_after_retry_error_with_safe_system_text():
    react = _react_module()
    context = _context()
    response = CopilotWorkflow(
        context.project_tools,
        react_agents=react.ReactAgentSuite(
            ErrorThenFinalModel(), registry=_registry_with_transient_calculator()
        ),
    ).invoke(
        ChatRequest(
            question="Calculate and publish the result.",
            route_override="agentic_rag",
        )
    )

    assert response.evaluation["stop_reason"] == "error"
    assert response.answer == "A read-only evidence tool failed, so no answer was published."
    assert "Done" not in response.answer
    assert response.grounded is False
    assert response.abstained is True


def test_workflow_enforces_request_max_steps_during_react_execution():
    react = _react_module()
    context = _context()
    response = CopilotWorkflow(
        context.project_tools,
        react_agents=react.ReactAgentSuite(ObservationDrivenModel()),
    ).invoke(
        ChatRequest(
            question="Why is ACT-STEEL-009 delayed and what is affected?",
            route_override="agentic_rag",
            max_steps=1,
        )
    )

    tool_events = [event for event in response.trace if event.stage == "tool"]
    assert len(tool_events) == 1
    assert response.evaluation["stop_reason"] == "step_limit"
    assert response.evaluation["within_step_limit"] is True
