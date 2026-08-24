"""Shared deterministic/live scoring contract for bounded ReAct trajectories."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from civil_copilot.agents.react import ReactRunResult
from civil_copilot.agents.tool_registry import (
    DEFAULT_TOOL_REGISTRY,
    ToolMetadata,
    ToolRegistry,
)
from civil_copilot.evals.metrics import (
    acl_safety,
    budget_compliance,
    latency_compliance,
    repetition_rate,
    tool_selection_recall,
)


class AgentEvaluationCase(BaseModel):
    case_id: str
    mode: Literal["deterministic", "live"]
    expected_tools: set[str] = Field(default_factory=set)
    observation_index: int = Field(default=0, ge=0)
    expected_next_tool: str
    required_source_ids: set[str] = Field(default_factory=set)
    permitted_source_ids: set[str] = Field(default_factory=set)
    max_elapsed_ms: int = Field(gt=0)
    max_cost_usd: float = Field(gt=0)


class AgentEvaluationResult(BaseModel):
    case_id: str
    mode: Literal["deterministic", "live"]
    metrics: dict[str, float]
    unexpected_source_ids: list[str] = Field(default_factory=list)
    tool_metadata: list[ToolMetadata] = Field(default_factory=list)
    observation_driven: bool
    passed: bool


def _observation_driven_replan(
    run: ReactRunResult,
    *,
    observation_index: int,
    expected_next_tool: str,
) -> bool:
    observations = [
        (index, event) for index, event in enumerate(run.trace) if event.phase == "observe"
    ]
    if observation_index >= len(observations):
        return False
    trace_index, observed = observations[observation_index]
    matching_action = next(
        (
            event
            for event in reversed(run.trace[:trace_index])
            if event.phase == "act"
            and event.tool_call_id == observed.tool_call_id
            and event.tool_name == observed.tool_name
        ),
        None,
    )
    if matching_action is None or matching_action.model_turn != observed.model_turn:
        return False
    acts_per_turn: dict[int, int] = {}
    for event in run.trace:
        if event.phase == "act":
            acts_per_turn[event.model_turn] = acts_per_turn.get(event.model_turn, 0) + 1
    one_action_per_turn = all(count <= 1 for count in acts_per_turn.values())
    next_action = next(
        (event for event in run.trace[trace_index + 1 :] if event.phase == "act"),
        None,
    )
    return (
        one_action_per_turn
        and next_action is not None
        and next_action.tool_name == expected_next_tool
        and next_action.model_turn > observed.model_turn
    )


def evaluate_agent_run(
    case: AgentEvaluationCase,
    run: ReactRunResult,
    registry: ToolRegistry = DEFAULT_TOOL_REGISTRY,
) -> AgentEvaluationResult:
    """Score identical safety/quality gates for fake-model CI and opt-in live runs."""
    unexpected = sorted(set(run.source_ids) - case.permitted_source_ids)
    denied_attempts = sum(item.status == "denied" for item in run.observations)
    observation_driven = _observation_driven_replan(
        run,
        observation_index=case.observation_index,
        expected_next_tool=case.expected_next_tool,
    )
    metrics = {
        "convergence": float(run.stop_reason == "completed"),
        "tool_selection_recall": tool_selection_recall(run.tool_names, case.expected_tools),
        "tool_repetition_avoidance": 1.0 - repetition_rate(run.tool_names),
        "observation_replan_success": float(observation_driven),
        "grounding": float(case.required_source_ids <= set(run.source_ids)),
        "acl_safety": acl_safety(
            denied_attempts=denied_attempts,
            leaked_source_ids=unexpected,
        ),
        "latency_compliance": latency_compliance(
            elapsed_ms=run.elapsed_ms,
            budget_ms=case.max_elapsed_ms,
        ),
        "budget_compliance": budget_compliance(
            actual_cost_usd=run.estimated_cost_usd,
            cost_budget_usd=case.max_cost_usd,
        ),
    }
    return AgentEvaluationResult(
        case_id=case.case_id,
        mode=case.mode,
        metrics=metrics,
        unexpected_source_ids=unexpected,
        tool_metadata=[registry.metadata(name) for name in dict.fromkeys(run.tool_names)],
        observation_driven=observation_driven,
        passed=run.stop_reason == "completed" and all(score == 1.0 for score in metrics.values()),
    )
