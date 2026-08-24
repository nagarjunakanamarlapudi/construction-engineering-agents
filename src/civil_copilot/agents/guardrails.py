"""Reusable bounded-run middleware for every Civil Copilot ReAct agent."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Callable
from time import monotonic
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolRetryMiddleware,
)
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages import BaseMessage

from civil_copilot.agents.tool_contracts import ReadOnlyToolObservation
from civil_copilot.agents.tool_registry import ToolRegistry
from civil_copilot.agents.tool_runtime import (
    AgentToolContext,
    SignalToolDeadlineRunner,
    ToolDeadlineExceeded,
    ToolDeadlineUnavailable,
)
from civil_copilot.agents.tools import ProjectTools


def token_cost_usd(
    messages: list[BaseMessage],
    *,
    input_cost_per_1k_tokens: float,
    output_cost_per_1k_tokens: float,
) -> float:
    """Compute a deterministic upper-bound estimate from standard usage metadata."""
    input_tokens = 0
    output_tokens = 0
    for message in messages:
        if not isinstance(message, AIMessage) or not message.usage_metadata:
            continue
        input_tokens += int(message.usage_metadata.get("input_tokens", 0))
        output_tokens += int(message.usage_metadata.get("output_tokens", 0))
    return (
        input_tokens * input_cost_per_1k_tokens + output_tokens * output_cost_per_1k_tokens
    ) / 1000


def _stop_message(
    reason: str,
    summary: str,
    *,
    usage_metadata: dict[str, int] | None = None,
    model_call_consumed: bool = False,
) -> AIMessage:
    return AIMessage(
        content=f"STOP_REASON:{reason}\n{summary}",
        usage_metadata=usage_metadata,
        additional_kwargs={
            "civil_copilot_control_stop": True,
            "civil_copilot_model_call_consumed": model_call_consumed,
        },
    )


def _usage(messages: list[BaseMessage]) -> dict[str, int] | None:
    input_tokens = 0
    output_tokens = 0
    for message in messages:
        if isinstance(message, AIMessage) and message.usage_metadata:
            input_tokens += int(message.usage_metadata.get("input_tokens", 0))
            output_tokens += int(message.usage_metadata.get("output_tokens", 0))
    if not input_tokens and not output_tokens:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _tool_signature(call: dict[str, Any]) -> str:
    return f"{call.get('name', '')}:{json.dumps(call.get('args', {}), sort_keys=True, default=str)}"


def _current_run_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=0,
    )
    return messages[latest_human:]


class BoundedRunMiddleware(AgentMiddleware):
    """Enforce wall-clock, token-cost, and identical-call repetition budgets."""

    def __init__(
        self,
        *,
        max_seconds: float,
        max_cost_usd: float | None,
        max_repeated_tool_calls: int,
        max_tool_calls: int,
        input_cost_per_1k_tokens: float,
        output_cost_per_1k_tokens: float,
    ) -> None:
        self.max_seconds = max_seconds
        self.max_cost_usd = max_cost_usd
        self.max_repeated_tool_calls = max_repeated_tool_calls
        self.max_tool_calls = max_tool_calls
        self.input_cost_per_1k_tokens = input_cost_per_1k_tokens
        self.output_cost_per_1k_tokens = output_cost_per_1k_tokens

    def _cost(self, messages: list[BaseMessage]) -> float:
        return token_cost_usd(
            messages,
            input_cost_per_1k_tokens=self.input_cost_per_1k_tokens,
            output_cost_per_1k_tokens=self.output_cost_per_1k_tokens,
        )

    def _elapsed(self, request: ModelRequest[AgentToolContext]) -> float:
        context = request.runtime.context if request.runtime else None
        started_at = context.started_at_monotonic if context else monotonic()
        return monotonic() - started_at

    def _time_exhausted(self, request: ModelRequest[AgentToolContext]) -> bool:
        context = request.runtime.context if request.runtime else None
        if context and context.deadline_monotonic is not None:
            return monotonic() >= context.deadline_monotonic
        return self._elapsed(request) >= self.max_seconds

    def _cost_cap(self, request: ModelRequest[AgentToolContext]) -> float | None:
        context = request.runtime.context if request.runtime else None
        if context and context.request_max_cost_usd is not None:
            return context.request_max_cost_usd
        return self.max_cost_usd

    def _request_cost(
        self,
        request: ModelRequest[AgentToolContext],
        messages: list[BaseMessage],
    ) -> float:
        context = request.runtime.context if request.runtime else None
        prior = context.prior_estimated_cost_usd if context else 0.0
        return prior + self._cost(messages)

    def _budget_stop(self, request: ModelRequest[AgentToolContext]) -> AIMessage | None:
        context = request.runtime.context if request.runtime else None
        current_messages = _current_run_messages(request.messages)
        completed_model_calls = sum(
            isinstance(message, AIMessage)
            and not (
                message.additional_kwargs.get("civil_copilot_control_stop")
                and not message.additional_kwargs.get("civil_copilot_model_call_consumed")
            )
            for message in current_messages
        )
        if (
            context
            and context.max_model_calls is not None
            and completed_model_calls >= context.max_model_calls
        ):
            return _stop_message("step_limit", "The investigation model-call budget was reached.")
        if self._time_exhausted(request):
            return _stop_message("time_limit", "The wall-clock investigation budget was reached.")
        cost_cap = self._cost_cap(request)
        if cost_cap is not None and self._request_cost(request, current_messages) >= cost_cap:
            return _stop_message("cost_limit", "The model cost budget was reached.")
        return None

    def wrap_model_call(
        self,
        request: ModelRequest[AgentToolContext],
        handler: Callable[[ModelRequest[AgentToolContext]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        if stopped := self._budget_stop(request):
            return stopped
        response = handler(request)
        current_messages = _current_run_messages(request.messages)
        messages = [*current_messages, *response.result]
        if self._time_exhausted(request):
            return _stop_message(
                "time_limit",
                "The wall-clock investigation budget was reached.",
                usage_metadata=_usage(response.result),
                model_call_consumed=True,
            )
        cost_cap = self._cost_cap(request)
        if cost_cap is not None and self._request_cost(request, messages) >= cost_cap:
            return _stop_message(
                "cost_limit",
                "The model cost budget was reached.",
                usage_metadata=_usage(response.result),
                model_call_consumed=True,
            )

        previous = Counter(
            _tool_signature(call)
            for message in current_messages
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        )
        proposed = [
            call
            for message in response.result
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        ]
        context = request.runtime.context if request.runtime else None
        request_cap = context.max_steps if context and context.max_steps else self.max_tool_calls
        completed_tools = sum(isinstance(message, ToolMessage) for message in current_messages)
        if proposed and completed_tools >= min(request_cap, self.max_tool_calls):
            return _stop_message(
                "step_limit",
                "The investigation step budget was reached.",
                usage_metadata=_usage(response.result),
                model_call_consumed=True,
            )
        if any(
            previous[_tool_signature(call)] >= self.max_repeated_tool_calls for call in proposed
        ):
            return _stop_message(
                "repetition",
                "The same tool call repeated without new evidence; human review may be needed.",
                usage_metadata=_usage(response.result),
                model_call_consumed=True,
            )
        return response


class SingleToolCallMiddleware(AgentMiddleware):
    """Serialize model-proposed parallel calls so every next action sees an observation."""

    @staticmethod
    def _one_call(message: AIMessage) -> AIMessage:
        if len(message.tool_calls) <= 1:
            return message
        retained = message.tool_calls[0]
        dropped = [call["id"] for call in message.tool_calls[1:]]
        return message.model_copy(
            update={
                "tool_calls": [retained],
                "additional_kwargs": {
                    **message.additional_kwargs,
                    "civil_copilot_single_tool_guard": {
                        "retained_call_id": retained["id"],
                        "dropped_call_ids": dropped,
                    },
                },
            }
        )

    def wrap_model_call(self, request, handler):
        response = handler(request)
        return ModelResponse(
            result=[
                self._one_call(message) if isinstance(message, AIMessage) else message
                for message in response.result
            ],
            structured_response=response.structured_response,
        )


class StructuredToolRetryMiddleware(ToolRetryMiddleware):
    """Use LangChain retries while preserving the typed, redacted observation contract."""

    def _handle_failure(
        self,
        tool_name: str,
        tool_call_id: str | None,
        exc: Exception,
        attempts_made: int,
    ) -> ToolMessage:
        observation = ReadOnlyToolObservation(
            tool_name=tool_name,
            status="error",
            summary="The transient tool operation exhausted its retry budget.",
            errors=[
                {
                    "code": "transient_failure",
                    "message": "The operation was not completed.",
                    "retryable": False,
                }
            ],
        )
        return ToolMessage(
            content=observation.model_dump_json(),
            tool_call_id=tool_call_id or "missing-tool-call-id",
            name=tool_name,
            status="error",
        )


class SingleAttemptStructuredToolMiddleware(StructuredToolRetryMiddleware):
    """Apply the same safe failure contract to tools whose native path is not retried."""


class RegistryToolBudgetMiddleware(AgentMiddleware):
    """Apply the registry's per-tool wall-clock envelope and safe error contract."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _budget_observation(
        *,
        tool_name: str,
        tool_call_id: str,
        elapsed_ms: int,
        code: str = "tool_time_limit",
    ) -> ToolMessage:
        if code == "tool_time_limit":
            summary = "The read-only tool exceeded its registered execution budget."
            message = "The operation did not continue after this timeout response."
        else:
            summary = "The read-only tool could not start with an enforceable deadline."
            message = "The operation was not started because no native deadline was available."
        observation = ReadOnlyToolObservation(
            tool_name=tool_name,
            status="error",
            summary=summary,
            errors=[
                {
                    "code": code,
                    "message": message,
                    "retryable": False,
                }
            ],
            elapsed_ms=elapsed_ms,
        )
        return ToolMessage(
            content=observation.model_dump_json(),
            tool_call_id=tool_call_id,
            name=tool_name,
        )

    def _run_direct_with_native_deadline(
        self,
        request,
        handler,
        specification,
        *,
        timeout_seconds: float | None = None,
    ):
        started = monotonic()
        try:
            return SignalToolDeadlineRunner().run(
                lambda: handler(request),
                tool_name=specification.name,
                timeout_seconds=timeout_seconds or specification.time_budget_seconds,
            )
        except ToolDeadlineUnavailable:
            return self._budget_observation(
                tool_name=specification.name,
                tool_call_id=request.tool_call["id"],
                elapsed_ms=int((monotonic() - started) * 1000),
                code="tool_deadline_unavailable",
            )
        except ToolDeadlineExceeded:
            return self._budget_observation(
                tool_name=specification.name,
                tool_call_id=request.tool_call["id"],
                elapsed_ms=int((monotonic() - started) * 1000),
            )

    def wrap_tool_call(self, request, handler):
        started = monotonic()
        specification = self.registry.get(request.tool_call["name"])
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        timeout_seconds = specification.time_budget_seconds
        if context is not None and context.deadline_monotonic is not None:
            remaining_seconds = context.deadline_monotonic - monotonic()
            if remaining_seconds <= 0:
                return self._budget_observation(
                    tool_name=specification.name,
                    tool_call_id=request.tool_call["id"],
                    elapsed_ms=0,
                )
            timeout_seconds = min(timeout_seconds, remaining_seconds)
        if context is None:
            return self._run_direct_with_native_deadline(
                request,
                handler,
                specification,
                timeout_seconds=timeout_seconds,
            )
        if context.tool_deadline_runner is not None:
            if getattr(context.tool_deadline_runner, "enforces_deadline", False) is not True:
                return self._budget_observation(
                    tool_name=specification.name,
                    tool_call_id=request.tool_call["id"],
                    elapsed_ms=int((monotonic() - started) * 1000),
                    code="tool_deadline_unavailable",
                )

            def operation():
                return handler(request)

            if getattr(
                context.tool_deadline_runner,
                "requires_native_deadline_proof",
                False,
            ):
                verifier = getattr(context.project_tools, "verified_tool_operation", None)
                if not callable(verifier):
                    return self._budget_observation(
                        tool_name=specification.name,
                        tool_call_id=request.tool_call["id"],
                        elapsed_ms=int((monotonic() - started) * 1000),
                        code="tool_deadline_unavailable",
                    )
                try:
                    operation = verifier(specification.name, operation)
                except ToolDeadlineUnavailable:
                    return self._budget_observation(
                        tool_name=specification.name,
                        tool_call_id=request.tool_call["id"],
                        elapsed_ms=int((monotonic() - started) * 1000),
                        code="tool_deadline_unavailable",
                    )
            try:
                return context.tool_deadline_runner.run(
                    operation,
                    tool_name=specification.name,
                    timeout_seconds=timeout_seconds,
                )
            except ToolDeadlineExceeded:
                return self._budget_observation(
                    tool_name=specification.name,
                    tool_call_id=request.tool_call["id"],
                    elapsed_ms=int((monotonic() - started) * 1000),
                )
            except ToolDeadlineUnavailable:
                return self._budget_observation(
                    tool_name=specification.name,
                    tool_call_id=request.tool_call["id"],
                    elapsed_ms=int((monotonic() - started) * 1000),
                    code="tool_deadline_unavailable",
                )
        if type(context.project_tools) is ProjectTools:
            return self._run_direct_with_native_deadline(
                request,
                handler,
                specification,
                timeout_seconds=timeout_seconds,
            )
        return self._budget_observation(
            tool_name=specification.name,
            tool_call_id=request.tool_call["id"],
            elapsed_ms=int((monotonic() - started) * 1000),
            code="tool_deadline_unavailable",
        )

    async def awrap_tool_call(self, request, handler):
        specification = self.registry.get(request.tool_call["name"])
        started = monotonic()
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        timeout_seconds = specification.time_budget_seconds
        if context is not None and context.deadline_monotonic is not None:
            timeout_seconds = min(
                timeout_seconds,
                max(context.deadline_monotonic - monotonic(), 0),
            )
        if timeout_seconds <= 0:
            return self._budget_observation(
                tool_name=specification.name,
                tool_call_id=request.tool_call["id"],
                elapsed_ms=0,
            )
        task = asyncio.create_task(handler(request))
        try:
            return await asyncio.wait_for(task, timeout=timeout_seconds)
        except TimeoutError:
            if task.done() and not task.cancelled():
                return task.result()
            observation = ReadOnlyToolObservation(
                tool_name=specification.name,
                status="error",
                summary="The read-only tool exceeded its registered execution budget.",
                errors=[
                    {
                        "code": "tool_time_limit",
                        "message": "The operation was cancelled at its registered time budget.",
                        "retryable": False,
                    }
                ],
                elapsed_ms=int((monotonic() - started) * 1000),
            )
            return ToolMessage(
                content=observation.model_dump_json(),
                tool_call_id=request.tool_call["id"],
                name=specification.name,
            )
