from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from civil_copilot.agents.react import ReactAgentConfig, ReactAgentSuite
from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.config import Settings
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.runtime import build_application_runtime


class SlowCostedFinalModel(BaseChatModel):
    delay_seconds: float
    second_delay_seconds: float | None = None
    input_tokens: int = 3
    output_tokens: int = 3
    _calls: int = PrivateAttr(default=0)

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def _llm_type(self) -> str:
        return "shared-budget-adversarial-model"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> SlowCostedFinalModel:
        return self

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        self._calls += 1
        delay = (
            self.second_delay_seconds
            if self._calls == 2 and self.second_delay_seconds is not None
            else self.delay_seconds
        )
        time.sleep(delay)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Completed this specialist investigation.",
                        usage_metadata={
                            "input_tokens": self.input_tokens,
                            "output_tokens": self.output_tokens,
                            "total_tokens": self.input_tokens + self.output_tokens,
                        },
                    )
                )
            ]
        )


def _actual_two_specialist_workflow(
    model: BaseChatModel,
    config: ReactAgentConfig,
) -> CopilotWorkflow:
    corpus = generate_demo_project(seed=800)
    tools = ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, lambda _query, _limit: []),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    return CopilotWorkflow(tools, react_agents=ReactAgentSuite(model, config=config))


def _compound_request() -> ChatRequest:
    return ChatRequest(
        question="What changed in S-204 Rev 5, and which activity was delayed?",
        route_override="agentic_rag",
        max_steps=6,
    )


def _delegated_roles(response: Any) -> list[str]:
    return [
        event.details["specialist"]
        for event in response.trace
        if event.stage == "plan"
        and event.title.startswith(("Delegate to", "Use general orchestrator"))
    ]


def test_two_real_specialists_share_one_wall_clock_deadline():
    model = SlowCostedFinalModel(delay_seconds=0.04, second_delay_seconds=0.07)
    workflow = _actual_two_specialist_workflow(
        model,
        ReactAgentConfig(
            max_seconds=0.1,
            max_cost_usd=1.0,
            input_cost_per_1k_tokens=1.0,
            output_cost_per_1k_tokens=1.0,
        ),
    )

    response = workflow.invoke(_compound_request())

    assert model.calls == 2
    assert _delegated_roles(response) == ["document", "schedule"]
    assert response.abstained is True
    assert response.evaluation["stop_reason"] == "time_limit"
    assert response.evaluation["elapsed_ms"] >= 100


def test_two_real_specialists_share_one_accumulated_model_cost_cap():
    model = SlowCostedFinalModel(delay_seconds=0.0)
    workflow = _actual_two_specialist_workflow(
        model,
        ReactAgentConfig(
            max_seconds=1.0,
            max_cost_usd=0.01,
            input_cost_per_1k_tokens=1.0,
            output_cost_per_1k_tokens=1.0,
        ),
    )

    response = workflow.invoke(_compound_request())

    assert model.calls == 2
    assert _delegated_roles(response) == ["document", "schedule"]
    assert response.abstained is True
    assert response.evaluation["stop_reason"] == "cost_limit"
    assert response.evaluation["estimated_cost_usd"] >= 0.01


def test_exhausted_first_specialist_prevents_the_next_handoff():
    model = SlowCostedFinalModel(delay_seconds=0.0)
    workflow = _actual_two_specialist_workflow(
        model,
        ReactAgentConfig(
            max_seconds=1.0,
            max_cost_usd=0.005,
            input_cost_per_1k_tokens=1.0,
            output_cost_per_1k_tokens=1.0,
        ),
    )

    response = workflow.invoke(_compound_request())

    assert model.calls == 1
    assert _delegated_roles(response) == ["document"]
    assert response.evaluation["stop_reason"] == "cost_limit"


def test_default_runtime_activates_nonzero_configured_model_pricing():
    settings = Settings(_env_file=None)
    application = build_application_runtime(
        settings=settings,
        corpus=generate_demo_project(seed=800),
    )
    try:
        assert settings.agent_input_cost_per_1k_tokens == 0.00025
        assert settings.agent_output_cost_per_1k_tokens == 0.002
        assert application.react_agents.config.input_cost_per_1k_tokens > 0
        assert application.react_agents.config.output_cost_per_1k_tokens > 0
        assert application.react_agents.config.max_cost_usd == settings.agent_max_cost_usd
    finally:
        application.close()
