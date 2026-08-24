"""Bounded LangChain v1 ReAct agents backed by the central tool registry."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import replace
from hashlib import sha256
from queue import Empty, Queue
from time import monotonic
from typing import Any, Literal, NotRequired
from urllib.parse import quote

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    wrap_tool_call,
)
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from civil_copilot.agents.guardrails import (
    BoundedRunMiddleware,
    RegistryToolBudgetMiddleware,
    SingleAttemptStructuredToolMiddleware,
    SingleToolCallMiddleware,
    StructuredToolRetryMiddleware,
    token_cost_usd,
)
from civil_copilot.agents.retry_policy import (
    HARD_DEADLINE_TOOL_NAMES,
    TRANSIENT_RETRY_TOOL_NAMES,
    TRANSIENT_TOOL_MAX_RETRIES,
)
from civil_copilot.agents.tool_contracts import ReadOnlyToolObservation
from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY, AgentRole, ToolRegistry
from civil_copilot.agents.tool_runtime import (
    AgentToolContext,
    MainThreadDeadlineDispatcher,
)

StopReason = Literal[
    "completed",
    "step_limit",
    "time_limit",
    "cost_limit",
    "repetition",
    "clarification",
    "abstained",
    "human_review",
    "agent_error",
    "error",
]

PUBLIC_STOP_MESSAGES: dict[StopReason, str] = {
    "human_review": ("This investigation requires human review before an answer can be published."),
    "clarification": (
        "More project detail is required before this investigation can continue safely."
    ),
    "step_limit": "The investigation reached its step limit without a publishable answer.",
    "time_limit": "The investigation reached its time limit without a publishable answer.",
    "cost_limit": "The investigation reached its cost limit without a publishable answer.",
    "repetition": ("The investigation stopped after repeated actions produced no safe resolution."),
    "error": "A read-only evidence tool failed, so no answer was published.",
    "agent_error": "The agent investigation failed safely, so no answer was published.",
    "abstained": "Permitted project evidence was insufficient to publish an answer.",
    "completed": "The investigation completed.",
}


def public_stop_message(reason: StopReason) -> str:
    """Return system-owned text for any result that must not expose model prose."""
    return PUBLIC_STOP_MESSAGES.get(
        reason,
        "The investigation stopped safely without a publishable answer.",
    )


class ReactAgentState(AgentState, total=False):
    brief_plan: list[str]
    evidence_ids: list[str]
    stop_reason: NotRequired[StopReason]


class ReactTraceEvent(BaseModel):
    phase: Literal["plan", "act", "observe", "decide", "safety"]
    title: str
    summary: str
    tool_name: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    tool_metadata: dict[str, Any] = Field(default_factory=dict)
    model_turn: int = Field(default=0, ge=0)
    tool_call_id: str | None = None


class ReactRunResult(BaseModel):
    role: AgentRole
    answer: str
    tool_names: list[str] = Field(default_factory=list)
    observations: list[ReadOnlyToolObservation] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    trace: list[ReactTraceEvent] = Field(default_factory=list)
    stop_reason: StopReason
    abstained: bool
    thread_id: str
    elapsed_ms: int = 0
    estimated_cost_usd: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0


class ReactAgentConfig(BaseModel):
    """Stable bounded-run configuration shared by all four compiled agents."""

    max_model_calls: int = Field(default=8, ge=1, le=32)
    max_tool_calls: int = Field(default=6, ge=1, le=24)
    max_repeated_tool_calls: int = Field(default=1, ge=1, le=8)
    max_seconds: float = Field(default=30.0, gt=0, le=300)
    max_cost_usd: float | None = Field(default=0.25, gt=0)
    input_cost_per_1k_tokens: float = Field(default=0.00025, ge=0)
    output_cost_per_1k_tokens: float = Field(default=0.002, ge=0)


class ReactRequestBudget(BaseModel):
    """One server-owned envelope shared by the supervisor and every specialist."""

    started_at_monotonic: float = Field(gt=0)
    deadline_monotonic: float = Field(gt=0)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_model_calls: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    spent_cost_usd: float = Field(default=0.0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)

    @classmethod
    def start(
        cls,
        config: ReactAgentConfig,
        *,
        max_tool_calls: int | None = None,
    ) -> ReactRequestBudget:
        started = monotonic()
        return cls(
            started_at_monotonic=started,
            deadline_monotonic=started + config.max_seconds,
            max_cost_usd=config.max_cost_usd,
            max_model_calls=config.max_model_calls,
            max_tool_calls=min(max_tool_calls or config.max_tool_calls, config.max_tool_calls),
        )

    @property
    def remaining_model_calls(self) -> int:
        return max(self.max_model_calls - self.model_calls, 0)

    @property
    def remaining_tool_calls(self) -> int:
        return max(self.max_tool_calls - self.tool_calls, 0)

    @property
    def elapsed_ms(self) -> int:
        return max(int((monotonic() - self.started_at_monotonic) * 1000), 0)

    def stop_reason(self) -> StopReason | None:
        if monotonic() >= self.deadline_monotonic:
            return "time_limit"
        if self.max_cost_usd is not None and self.spent_cost_usd >= self.max_cost_usd:
            return "cost_limit"
        if self.remaining_model_calls == 0 or self.remaining_tool_calls == 0:
            return "step_limit"
        return None

    def tool_stop_reason(self) -> StopReason | None:
        """Return only limits that prevent a supervisor-owned tool action."""
        if monotonic() >= self.deadline_monotonic:
            return "time_limit"
        if self.max_cost_usd is not None and self.spent_cost_usd >= self.max_cost_usd:
            return "cost_limit"
        if self.remaining_tool_calls == 0:
            return "step_limit"
        return None

    def consume(self, result: ReactRunResult) -> None:
        self.spent_cost_usd += result.estimated_cost_usd
        self.model_calls += result.model_calls
        self.tool_calls += result.tool_calls

    def reserve_tool_call(self) -> None:
        """Count a supervisor tool before execution so a later action cannot race the cap."""
        if stopped := self.tool_stop_reason():
            raise RuntimeError(f"shared request budget exhausted: {stopped}")
        self.tool_calls += 1

    def public_snapshot(self) -> dict[str, int | float | None]:
        return {
            "elapsed_ms": self.elapsed_ms,
            "remaining_model_calls": self.remaining_model_calls,
            "remaining_tool_calls": self.remaining_tool_calls,
            "estimated_cost_usd": self.spent_cost_usd,
            "max_cost_usd": self.max_cost_usd,
        }


def _safe_tool_error(error: Exception, tool_name: str) -> ReadOnlyToolObservation:
    denied = isinstance(error, PermissionError)
    invalid = isinstance(error, (ValueError, KeyError))
    code = (
        "permission_denied"
        if denied
        else "invalid_tool_request"
        if invalid
        else "unexpected_tool_failure"
    )
    return ReadOnlyToolObservation(
        tool_name=tool_name,
        status="denied" if denied else "error",
        summary=(
            "The requested operation is outside the permitted project scope."
            if denied
            else "The tool could not complete the validated read-only operation."
        ),
        errors=[
            {
                "code": code,
                "message": "The request was not executed.",
                "retryable": False,
            }
        ],
        elapsed_ms=0,
    )


@wrap_tool_call
def redact_expected_tool_errors(request, handler):
    """Return safe structured observations without exposing store or ACL details."""
    try:
        return handler(request)
    except (TimeoutError, ConnectionError):
        raise
    except Exception as error:
        observation = _safe_tool_error(error, request.tool_call["name"])
        return ToolMessage(
            content=observation.model_dump_json(),
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )


CONVERGENCE_INSTRUCTIONS = (
    " The tool limit is a safety ceiling, not a target. Start with the single highest-value "
    "tool. After a successful observation returns relevant evidence and source identifiers, "
    "answer immediately unless one different evidence step is strictly necessary for your "
    "assigned responsibility. Never repeat the same tool with the same arguments or reformulate "
    "a successful search. Cover only your assigned specialist responsibility; the supervisor "
    "combines evidence from other specialists."
)


ROLE_PROMPTS: dict[AgentRole, str] = {
    "orchestrator": (
        "You are the Copilot Orchestrator. Make a brief bounded plan, call one read-only tool "
        "at a time, inspect every structured observation, and decide whether to stop or take the "
        "next evidence-producing step. Never reveal hidden chain-of-thought. Ask for clarification "
        "or abstain when permitted evidence cannot resolve the question." + CONVERGENCE_INSTRUCTIONS
    ),
    "document": (
        "You are the Document specialist. Use only document, record, and revision tools. Return "
        "source identifiers and distinguish sourced facts from inference."
        + CONVERGENCE_INSTRUCTIONS
    ),
    "schedule": (
        "You are the Schedule specialist. Use only permitted record, graph, schedule, and "
        "deterministic calculation tools. Inspect observations before choosing the next step."
        + CONVERGENCE_INSTRUCTIONS
    ),
    "risk": (
        "You are the Risk specialist. Rank only issues supported by permitted document, record, "
        "graph, schedule, or deterministic calculation observations; do not invent project facts."
        + CONVERGENCE_INSTRUCTIONS
    ),
}


class ReactAgentSuite:
    """Create the orchestrator and three bounded specialist ReAct graphs once."""

    def __init__(
        self,
        model: BaseChatModel | str,
        *,
        registry: ToolRegistry = DEFAULT_TOOL_REGISTRY,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        config: ReactAgentConfig | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        max_model_calls: int | None = None,
        max_tool_calls: int | None = None,
    ) -> None:
        self.registry = registry
        self.checkpointer = checkpointer or InMemorySaver()
        bounded = config or ReactAgentConfig()
        overrides: dict[str, int] = {}
        if max_model_calls is not None:
            overrides["max_model_calls"] = max_model_calls
        if max_tool_calls is not None:
            overrides["max_tool_calls"] = max_tool_calls
        self.config = bounded.model_copy(update=overrides)
        self.max_model_calls = self.config.max_model_calls
        self.max_tool_calls = self.config.max_tool_calls
        agent_middleware = [
            ModelCallLimitMiddleware(run_limit=self.config.max_model_calls, exit_behavior="end"),
            ToolCallLimitMiddleware(run_limit=self.config.max_tool_calls, exit_behavior="continue"),
            BoundedRunMiddleware(
                max_seconds=self.config.max_seconds,
                max_cost_usd=self.config.max_cost_usd,
                max_repeated_tool_calls=self.config.max_repeated_tool_calls,
                max_tool_calls=self.config.max_tool_calls,
                input_cost_per_1k_tokens=self.config.input_cost_per_1k_tokens,
                output_cost_per_1k_tokens=self.config.output_cost_per_1k_tokens,
            ),
            SingleToolCallMiddleware(),
            SingleAttemptStructuredToolMiddleware(
                max_retries=0,
                tools=list(HARD_DEADLINE_TOOL_NAMES),
                retry_on=(TimeoutError, ConnectionError),
                backoff_factor=0.0,
                initial_delay=0.0,
                jitter=False,
            ),
            StructuredToolRetryMiddleware(
                max_retries=TRANSIENT_TOOL_MAX_RETRIES,
                tools=list(TRANSIENT_RETRY_TOOL_NAMES),
                retry_on=(TimeoutError, ConnectionError),
                backoff_factor=0.0,
                initial_delay=0.0,
                jitter=False,
            ),
            RegistryToolBudgetMiddleware(registry),
            redact_expected_tool_errors,
            *middleware,
        ]
        self.agents = {
            role: create_agent(
                model=model,
                tools=registry.tools_for(role),
                system_prompt=ROLE_PROMPTS[role],
                middleware=agent_middleware,
                state_schema=ReactAgentState,
                context_schema=AgentToolContext,
                checkpointer=self.checkpointer,
                name=f"civil_copilot_{role}",
            )
            for role in ("orchestrator", "document", "schedule", "risk")
        }

    def tool_names(self, role: AgentRole) -> set[str]:
        return {tool.name for tool in self.registry.tools_for(role)}

    @staticmethod
    def thread_id(role: AgentRole, context: AgentToolContext) -> str:
        """Return the canonical, permission-scoped conversation checkpoint identity."""
        conversation_id = context.conversation_id
        if not conversation_id:
            raise ValueError("conversation_id must be non-empty")
        acl_fingerprint = sha256(
            "\0".join(sorted(set(context.access_scopes))).encode()
        ).hexdigest()[:16]
        return "|".join(
            (
                f"project={quote(context.project_id, safe='-_.~')}",
                f"user={quote(context.user_id, safe='-_.~')}",
                f"role={role}",
                f"conversation={quote(conversation_id, safe='-_.~')}",
                f"acl={acl_fingerprint}",
            )
        )

    _thread_id = thread_id

    def _config(
        self,
        role: AgentRole,
        context: AgentToolContext,
        callbacks: Sequence[BaseCallbackHandler] = (),
    ) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": self._thread_id(role, context)},
            "callbacks": list(callbacks),
            "metadata": {
                "agent_role": role,
                "project_id": context.project_id,
                "user_id": context.user_id,
                "request_id": context.request_id,
                "conversation_id": context.conversation_id,
            },
        }

    def _input(self, question: str) -> ReactAgentState:
        return {
            "messages": [HumanMessage(content=question)],
            "brief_plan": ["Select one permitted evidence step and inspect its observation."],
            "evidence_ids": [],
        }

    @staticmethod
    def _observation(message: ToolMessage) -> ReadOnlyToolObservation | None:
        content = message.content
        if not isinstance(content, str):
            return None
        try:
            return ReadOnlyToolObservation.model_validate_json(content)
        except ValueError:
            return None

    def _result(
        self,
        role: AgentRole,
        thread_id: str,
        values: dict[str, Any],
    ) -> ReactRunResult:
        all_messages = values.get("messages", [])
        latest_human = max(
            (
                index
                for index, message in enumerate(all_messages)
                if isinstance(message, HumanMessage)
            ),
            default=0,
        )
        messages = all_messages[latest_human:]
        observations: list[ReadOnlyToolObservation] = []
        trace = [
            ReactTraceEvent(
                phase="plan",
                title="Bounded investigation plan",
                summary="Select one permitted evidence step and inspect its observation.",
                model_turn=0,
            )
        ]
        model_turn = 0
        actual_model_calls = 0
        actual_tool_calls = 0
        pending_observation: ReadOnlyToolObservation | None = None
        for message in messages:
            if isinstance(message, AIMessage):
                model_turn += 1
                if not (
                    message.additional_kwargs.get("civil_copilot_control_stop")
                    and not message.additional_kwargs.get("civil_copilot_model_call_consumed")
                ):
                    actual_model_calls += 1
                guard = message.additional_kwargs.get("civil_copilot_single_tool_guard")
                if guard:
                    trace.append(
                        ReactTraceEvent(
                            phase="safety",
                            title="Serialized parallel tool proposal",
                            summary=(
                                "Only the first read-only action was retained; later actions "
                                "must be chosen after its observation."
                            ),
                            model_turn=model_turn,
                            tool_call_id=guard["retained_call_id"],
                        )
                    )
                if pending_observation is not None:
                    trace.append(
                        ReactTraceEvent(
                            phase="decide",
                            title="Observation informed the next decision",
                            summary=(
                                "The next action or stop was selected after the latest "
                                "structured observation."
                            ),
                            tool_name=pending_observation.tool_name,
                            source_ids=pending_observation.source_ids,
                            tool_metadata=self.registry.metadata(
                                pending_observation.tool_name
                            ).model_dump(),
                            model_turn=model_turn,
                        )
                    )
                    pending_observation = None
                for call in message.tool_calls:
                    trace.append(
                        ReactTraceEvent(
                            phase="act",
                            title=f"Call {call['name']}",
                            summary="Executing one typed read-only operation.",
                            tool_name=call["name"],
                            tool_metadata=self.registry.metadata(call["name"]).model_dump(),
                            model_turn=model_turn,
                            tool_call_id=call["id"],
                        )
                    )
            elif isinstance(message, ToolMessage):
                actual_tool_calls += 1
                observation = self._observation(message)
                if observation is None:
                    continue
                observations.append(observation)
                trace.append(
                    ReactTraceEvent(
                        phase="observe",
                        title=f"Observed {observation.tool_name}",
                        summary=observation.summary,
                        tool_name=observation.tool_name,
                        source_ids=observation.source_ids,
                        tool_metadata=self.registry.metadata(observation.tool_name).model_dump(),
                        model_turn=model_turn,
                        tool_call_id=message.tool_call_id,
                    )
                )
                pending_observation = observation
        tool_names = [observation.tool_name for observation in observations]
        source_ids = list(
            dict.fromkeys(source_id for item in observations for source_id in item.source_ids)
        )
        final_text = next(
            (
                str(message.content)
                for message in reversed(messages)
                if isinstance(message, AIMessage) and message.content and not message.tool_calls
            ),
            "",
        )
        control = re.match(
            r"^STOP_REASON:(clarification|abstained|human_review|time_limit|cost_limit|repetition|step_limit|agent_error|error)\s*\n?",
            final_text,
        )
        model_limit = "model call limit" in final_text.lower()
        if model_limit:
            stop_reason: StopReason = "step_limit"
            final_text = "The bounded investigation reached its model-step limit."
        elif control:
            stop_reason = control.group(1)  # type: ignore[assignment]
            final_text = final_text[control.end() :].strip()
        elif any(observation.status == "error" for observation in observations):
            stop_reason = "error"
        elif any(observation.status == "denied" for observation in observations) and not source_ids:
            stop_reason: StopReason = "abstained"
        elif final_text:
            stop_reason = "completed"
        elif len(tool_names) >= self.max_tool_calls:
            stop_reason: StopReason = "step_limit"
        else:
            stop_reason = "abstained"
        elapsed_ms = max(
            int((monotonic() - values.get("started_at_monotonic", monotonic())) * 1000),
            max((observation.elapsed_ms for observation in observations), default=0),
        )
        estimated_cost = token_cost_usd(
            list(messages),
            input_cost_per_1k_tokens=self.config.input_cost_per_1k_tokens,
            output_cost_per_1k_tokens=self.config.output_cost_per_1k_tokens,
        )
        return ReactRunResult(
            role=role,
            answer=(final_text if stop_reason == "completed" else public_stop_message(stop_reason)),
            tool_names=tool_names,
            observations=observations,
            source_ids=source_ids,
            trace=trace,
            stop_reason=stop_reason,
            abstained=stop_reason != "completed",
            thread_id=thread_id,
            elapsed_ms=elapsed_ms,
            estimated_cost_usd=estimated_cost,
            model_calls=actual_model_calls,
            tool_calls=actual_tool_calls,
        )

    def _stopped_result(
        self,
        *,
        role: AgentRole,
        thread_id: str,
        reason: StopReason,
    ) -> ReactRunResult:
        return ReactRunResult(
            role=role,
            answer=public_stop_message(reason),
            stop_reason=reason,
            abstained=True,
            thread_id=thread_id,
            trace=[
                ReactTraceEvent(
                    phase="safety",
                    title=f"Shared request budget stopped before {role} specialist",
                    summary=(
                        "The end-to-end request budget was exhausted before another "
                        "model or tool action could start."
                    ),
                )
            ],
        )

    def run(
        self,
        *,
        role: AgentRole,
        question: str,
        context: AgentToolContext,
        callbacks: Sequence[BaseCallbackHandler] = (),
        max_steps: int | None = None,
        budget: ReactRequestBudget | None = None,
    ) -> ReactRunResult:
        shared_budget = budget or ReactRequestBudget.start(
            self.config,
            max_tool_calls=max_steps,
        )
        thread_id = self._thread_id(role, context)
        if stopped := shared_budget.stop_reason():
            return self._stopped_result(role=role, thread_id=thread_id, reason=stopped)
        effective_steps = min(
            max_steps or self.max_tool_calls,
            self.max_tool_calls,
            shared_budget.remaining_tool_calls,
        )
        context = replace(
            context,
            max_steps=effective_steps,
            max_model_calls=shared_budget.remaining_model_calls,
            deadline_monotonic=shared_budget.deadline_monotonic,
            prior_estimated_cost_usd=shared_budget.spent_cost_usd,
            request_max_cost_usd=shared_budget.max_cost_usd,
            started_at_monotonic=monotonic(),
        )
        config = self._config(role, context, callbacks)
        if threading.current_thread() is threading.main_thread():
            dispatcher = MainThreadDeadlineDispatcher()
            context = replace(context, tool_deadline_runner=dispatcher.runner())
            copied_context = copy_context()

            def invoke_agent():
                return copied_context.run(
                    self.agents[role].invoke,
                    self._input(question),
                    config=config,
                    context=context,
                    version="v2",
                )

            with ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="civil-react",
            ) as executor:
                future = executor.submit(invoke_agent)
                try:
                    while not future.done():
                        dispatcher.service_one()
                    output = future.result()
                finally:
                    dispatcher.close()
        else:
            output = self.agents[role].invoke(
                self._input(question),
                config=config,
                context=context,
                version="v2",
            )
        values = output.value if hasattr(output, "value") else output
        values["started_at_monotonic"] = context.started_at_monotonic
        result = self._result(role, thread_id, values)
        shared_budget.consume(result)
        return result

    def stream(
        self,
        *,
        role: AgentRole,
        question: str,
        context: AgentToolContext,
        callbacks: Sequence[BaseCallbackHandler] = (),
        max_steps: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        effective_steps = min(max_steps or self.max_tool_calls, self.max_tool_calls)
        context = replace(
            context,
            max_steps=effective_steps,
            started_at_monotonic=monotonic(),
        )
        config = self._config(role, context, callbacks)
        if threading.current_thread() is not threading.main_thread():
            yield from self.agents[role].stream(
                self._input(question),
                config=config,
                context=context,
                stream_mode=["updates", "custom"],
                version="v2",
            )
            return

        dispatcher = MainThreadDeadlineDispatcher()
        context = replace(context, tool_deadline_runner=dispatcher.runner())
        chunks: Queue[tuple[str, Any]] = Queue()
        copied_context = copy_context()

        def produce_chunks() -> None:
            try:
                for chunk in copied_context.run(
                    self.agents[role].stream,
                    self._input(question),
                    config=config,
                    context=context,
                    stream_mode=["updates", "custom"],
                    version="v2",
                ):
                    chunks.put(("chunk", chunk))
            except BaseException as error:
                chunks.put(("error", error))
            finally:
                chunks.put(("done", None))

        with ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="civil-react-stream",
        ) as executor:
            future = executor.submit(produce_chunks)
            done = False
            try:
                while not done:
                    dispatcher.service_one(wait_seconds=0.005)
                    try:
                        kind, payload = chunks.get(timeout=0.005)
                    except Empty:
                        continue
                    if kind == "chunk":
                        yield payload
                    elif kind == "error":
                        raise payload
                    else:
                        done = True
                future.result()
            finally:
                dispatcher.close()

    def checkpoint(self, role: AgentRole, context: AgentToolContext):
        return self.agents[role].get_state(
            {"configurable": {"thread_id": self._thread_id(role, context)}}
        )
