"""Build the domain-neutral LangChain middleware teaching notebook."""

from __future__ import annotations

from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "notebooks" / "10_langchain_middleware_primer.ipynb"

SOURCE = r'''# %% [markdown]
# 10 — LangChain Middleware Primer: See Every Agent Lifecycle Stage

> **DOMAIN-NEUTRAL PRIMER:** This notebook explains middleware using ordinary assistant examples. It does not depend on a particular business domain.

Middleware is code that runs **around** an agent's normal work. It can observe, modify, protect, retry, limit, or pause execution without putting those concerns inside every tool or prompt.

This notebook answers:

1. When does each middleware hook run?
2. Why do some hooks run once while others run repeatedly?
3. What is the difference between node-style and wrap-style hooks?
4. When should we write custom middleware versus use a built-in class?
5. How do retries, fallbacks, limits, PII protection, summarization, and human approval behave?
6. How can we test middleware without spending model credits?

# %% [markdown]
## One agent invocation, stage by stage

![Middleware across one agent run](../docs/images/middleware-agent-lifecycle.svg)

The most important detail is the **loop**:

- `before_agent` and `after_agent` normally run once per invocation.
- `before_model`, `wrap_model_call`, and `after_model` run for every model call.
- `wrap_tool_call` runs for every tool execution.
- After a tool observation, the agent returns to the model and the model hooks run again.

# %% [markdown]
## What middleware is good for

![Middleware capability map](../docs/images/middleware-capability-map.svg)

| Need | Typical middleware boundary |
|---|---|
| Logging, traces, usage, timing | Around the agent, model, or tool |
| Dynamic prompt, model, or available tools | Before or around the model |
| PII filtering and output validation | Before/after the model or around tools |
| Retry and fallback | Around the failing operation |
| Model/tool call budgets | Before model or tool execution |
| Human approval | Before a sensitive tool executes |
| Long-conversation compression | Before the model receives context |

Middleware is for **cross-cutting behavior**. The actual business operation still belongs in a tool or application service.

# %% [markdown]
## Three execution modes

| Mode | Model | Requirement | Purpose |
|---|---|---|---|
| `model_free` | Deterministic `BaseChatModel` test double | Nothing external | Runs every lifecycle and built-in middleware example predictably |
| `ollama_gemma4` | `gemma4:e4b` | Local Ollama and downloaded model | Repeats the main tool-using agent with a local model |
| `openai` | `gpt-5-mini` | `OPENAI_API_KEY` | Repeats the main agent with OpenAI |

The model-free path still uses the real `create_agent()`, real LangGraph execution, real `@tool` functions, and real middleware. Only the model response is scripted.

Launch an optional provider mode with:

```bash
MIDDLEWARE_PRIMER_MODE=ollama_gemma4 uv run jupyter lab notebooks/10_langchain_middleware_primer.ipynb
MIDDLEWARE_PRIMER_MODE=openai uv run jupyter lab notebooks/10_langchain_middleware_primer.ipynb
```

# %%
import html
import json
import os
from collections.abc import Sequence
from importlib.metadata import version
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from IPython.display import HTML, display
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
    dynamic_prompt,
)
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import Field

if os.getenv("MIDDLEWARE_PRIMER_LOAD_DOTENV", "1") == "1":
    load_dotenv()

MODE = os.getenv("MIDDLEWARE_PRIMER_MODE", "model_free").strip().lower()
VALID_MODES = {"model_free", "ollama_gemma4", "openai"}
if MODE not in VALID_MODES:
    raise ValueError(f"MIDDLEWARE_PRIMER_MODE must be one of {sorted(VALID_MODES)}")

AUTO_REVIEW = os.getenv("MIDDLEWARE_PRIMER_AUTO_REVIEW", "1") == "1"

print(
    f"mode={MODE} langchain={version('langchain')} langgraph={version('langgraph')} "
    f"openai_key_configured={bool(os.getenv('OPENAI_API_KEY'))}"
)

# %%
def card(title: str, body: str, color: str = "#4338ca") -> None:
    display(
        HTML(
            f"""
            <div style="border:1px solid #dbeafe;border-left:6px solid {color};
                        border-radius:12px;padding:14px 18px;margin:10px 0;
                        background:#fff;font-family:system-ui;">
              <div style="font-weight:750;font-size:17px;color:#111827">{html.escape(title)}</div>
              <div style="margin-top:6px;color:#374151;line-height:1.5">{body}</div>
            </div>
            """
        )
    )


def table(rows: list[tuple[str, str]]) -> None:
    body = "".join(
        f"<tr><td style='font-weight:700;padding:7px 12px'>{html.escape(left)}</td>"
        f"<td style='padding:7px 12px'>{html.escape(right)}</td></tr>"
        for left, right in rows
    )
    display(
        HTML(
            "<table style='border-collapse:collapse;width:100%;font-family:system-ui'>"
            f"{body}</table>"
        )
    )


STAGE_COLORS = {
    "agent": "#2563eb",
    "model": "#7c3aed",
    "tool": "#059669",
}


def render_lifecycle(events: list[dict[str, Any]]) -> None:
    """Show the public middleware event timeline, not hidden model reasoning."""
    for index, event in enumerate(events, start=1):
        group = event["group"]
        details = html.escape(json.dumps(event.get("details", {}), sort_keys=True))
        card(
            f"{index}. {event['stage']}",
            f"<code>{details}</code>",
            STAGE_COLORS[group],
        )


def render_messages(messages: list[BaseMessage]) -> None:
    """Render model responses, tool calls, arguments, observations, and final answer."""
    for index, message in enumerate(messages, start=1):
        if isinstance(message, HumanMessage):
            card(f"{index}. User message", html.escape(str(message.content)), "#2563eb")
        elif isinstance(message, ToolMessage):
            card(
                f"{index}. Tool observation · {message.name or 'tool'}",
                f"<pre style='white-space:pre-wrap'>{html.escape(str(message.content))}</pre>",
                "#059669",
            )
        elif isinstance(message, AIMessage):
            if message.tool_calls:
                calls = "".join(
                    "<div><b>Tool:</b> "
                    + html.escape(str(call.get("name")))
                    + "<br><b>Arguments:</b> <code>"
                    + html.escape(json.dumps(call.get("args", {}), sort_keys=True))
                    + "</code></div>"
                    for call in message.tool_calls
                )
                card(f"{index}. Model requested tool", calls, "#7c3aed")
            if message.content:
                label = "Final answer" if index == len(messages) else "Model response"
                card(f"{index}. {label}", html.escape(str(message.content)), "#7c3aed")

# %% [markdown]
## Part 1 — A deterministic model that still runs through `create_agent()`

The model-free path must exercise the framework, not imitate an agent loop with handwritten Python. `LifecycleScriptModel` is therefore a small `BaseChatModel` implementation that returns one valid tool call and then a final answer after seeing the tool observation.

This is a **test double**, not a production model. It makes the lifecycle repeatable and free of network calls.

# %%
MODEL_CALL_COUNTS: dict[str, int] = {}


class LifecycleScriptModel(BaseChatModel):
    tool_name: str | None = "lookup_status"
    tool_args: dict[str, Any] = Field(
        default_factory=lambda: {"reference_id": "CASE-42"}
    )
    final_text: str = "CASE-42 is ready for review."
    repeat_tool_calls: int = 1
    fail_on_call: bool = False
    echo_human: bool = False
    counter_key: str = ""
    bound_tool_names: frozenset[str] = Field(default_factory=frozenset, exclude=True)

    @property
    def _llm_type(self) -> str:
        return "middleware-primer-scripted-model"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        names = frozenset(tool.name for tool in tools if isinstance(tool, BaseTool))
        return self.model_copy(update={"bound_tool_names": names})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.counter_key:
            MODEL_CALL_COUNTS[self.counter_key] = MODEL_CALL_COUNTS.get(self.counter_key, 0) + 1
        if self.fail_on_call:
            raise RuntimeError("The primary teaching model is intentionally unavailable.")
        if self.echo_human:
            latest = next(
                message for message in reversed(messages) if isinstance(message, HumanMessage)
            )
            response = AIMessage(content=str(latest.content))
        else:
            observations = [message for message in messages if isinstance(message, ToolMessage)]
            if (
                self.tool_name
                and self.tool_name in self.bound_tool_names
                and len(observations) < self.repeat_tool_calls
            ):
                response = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": self.tool_name,
                            "args": self.tool_args,
                            "id": f"scripted-{len(observations) + 1}-{self.tool_name}",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                response = AIMessage(content=self.final_text)
        return ChatResult(generations=[ChatGeneration(message=response)])


# %%
def build_chat_model(mode: str):
    if mode == "model_free":
        return LifecycleScriptModel()
    if mode == "ollama_gemma4":
        return ChatOllama(
            model="gemma4:e4b",
            temperature=0,
            validate_model_on_init=True,
        )
    if mode == "openai":
        return ChatOpenAI(
            model="gpt-5-mini",
            reasoning_effort="low",
            timeout=30,
            max_retries=0,
        )
    raise ValueError(f"Unsupported middleware primer mode: {mode}")

# %% [markdown]
## Part 2 — One custom class covering all six lifecycle hooks

Use a class when several hooks share configuration or collected state. Use decorators later when one focused hook is enough.

The middleware below records public execution facts only. It does not expose hidden chain-of-thought.

This notebook follows the synchronous `invoke()` path. A production middleware class used with `ainvoke()` should provide the corresponding async hooks—such as `abefore_model`, `awrap_model_call`, and `awrap_tool_call`—when its work is asynchronous.

# %%
@tool
def lookup_status(reference_id: str) -> str:
    """Look up the status of one fictional reference."""
    return json.dumps(
        {
            "reference_id": reference_id,
            "status": "ready for review",
            "source": "deterministic teaching data",
        }
    )


class LifecycleMiddleware(AgentMiddleware):
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events

    def _record(self, stage: str, group: str, **details: Any) -> None:
        self.events.append({"stage": stage, "group": group, "details": details})

    def before_agent(self, state, runtime):
        self._record("before_agent", "agent", message_count=len(state["messages"]))

    def before_model(self, state, runtime):
        self._record("before_model", "model", message_count=len(state["messages"]))

    def wrap_model_call(self, request, handler):
        self._record(
            "wrap_model_call.before",
            "model",
            available_tools=[tool.name for tool in request.tools],
        )
        response = handler(request)
        self._record(
            "wrap_model_call.after",
            "model",
            returned_messages=len(response.result),
        )
        return response

    def after_model(self, state, runtime):
        latest = state["messages"][-1]
        self._record(
            "after_model",
            "model",
            requested_tools=[call["name"] for call in getattr(latest, "tool_calls", [])],
        )

    def wrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        self._record(
            f"wrap_tool_call.before:{tool_name}",
            "tool",
            arguments=request.tool_call["args"],
        )
        result = handler(request)
        self._record(
            f"wrap_tool_call.after:{tool_name}",
            "tool",
            result_type=type(result).__name__,
        )
        return result

    def after_agent(self, state, runtime):
        self._record("after_agent", "agent", message_count=len(state["messages"]))


lifecycle_events: list[dict[str, Any]] = []
lifecycle_agent = create_agent(
    model=LifecycleScriptModel(),
    tools=[lookup_status],
    system_prompt=(
        "You are a teaching assistant. Use lookup_status when a reference status is requested. "
        "After the observation, answer in one sentence."
    ),
    middleware=[LifecycleMiddleware(lifecycle_events)],
)
lifecycle_result = lifecycle_agent.invoke(
    {"messages": [HumanMessage(content="What is the status of CASE-42?")]}
)

render_messages(lifecycle_result["messages"])
render_lifecycle(lifecycle_events)

expected_lifecycle = [
    "before_agent",
    "before_model",
    "wrap_model_call.before",
    "wrap_model_call.after",
    "after_model",
    "wrap_tool_call.before:lookup_status",
    "wrap_tool_call.after:lookup_status",
    "before_model",
    "wrap_model_call.before",
    "wrap_model_call.after",
    "after_model",
    "after_agent",
]
lifecycle_names = [event["stage"] for event in lifecycle_events]
lifecycle_order_ok = lifecycle_names == expected_lifecycle
print("LIFECYCLE_EVENTS " + json.dumps(lifecycle_names))
print(f"LIFECYCLE_ORDER_OK {lifecycle_order_ok}")

# %% [markdown]
### Reading the trace

The first model call asks for `lookup_status`. The tool wrapper observes the arguments and result. The agent then loops back to the model, so the model hooks execute a second time. The second model response contains no tool call, so execution reaches `after_agent`.

When several middleware objects are installed:

- `before_*` hooks run in list order;
- `after_*` hooks run in reverse order;
- `wrap_*` hooks nest, with the first middleware acting as the outer wrapper.

# %% [markdown]
## Part 3 — Decorator middleware for one focused responsibility

`@dynamic_prompt` is middleware specialized for building a system prompt from the current request. A decorator is ideal here because only one hook is needed.

# %%
dynamic_prompt_events: list[str] = []


@dynamic_prompt
def audience_aware_prompt(request) -> str:
    dynamic_prompt_events.append("dynamic_prompt")
    return (
        "You are a concise teaching assistant. Explain framework terms in plain language "
        "and do not assume prior agent knowledge."
    )


dynamic_prompt_agent = create_agent(
    model=LifecycleScriptModel(tool_name=None, final_text="Middleware surrounds agent steps."),
    tools=[],
    system_prompt="Base teaching instructions.",
    middleware=[audience_aware_prompt],
)
dynamic_prompt_result = dynamic_prompt_agent.invoke(
    {"messages": [HumanMessage(content="Explain middleware briefly.")]}
)
dynamic_prompt_ok = dynamic_prompt_events == ["dynamic_prompt"]
render_messages(dynamic_prompt_result["messages"])
print(f"DYNAMIC_PROMPT_OK {dynamic_prompt_ok}")

# %% [markdown]
## Part 4 — Resilience: retry a tool and fall back from a model

Retries are appropriate for explicitly transient failures. They should be bounded and should not blindly repeat irreversible writes. Model fallback changes the model when the primary model call fails.

# %%
flaky_attempts = {"count": 0}


@tool
def flaky_lookup(reference_id: str) -> str:
    """Return a fictional record after one simulated transient connection failure."""
    flaky_attempts["count"] += 1
    if flaky_attempts["count"] == 1:
        raise ConnectionError("Simulated temporary connection failure")
    return f"{reference_id} recovered on retry"


retry_agent = create_agent(
    model=LifecycleScriptModel(
        tool_name="flaky_lookup",
        tool_args={"reference_id": "CASE-7"},
        final_text="CASE-7 was recovered after a bounded retry.",
    ),
    tools=[flaky_lookup],
    middleware=[
        ToolRetryMiddleware(
            max_retries=1,
            initial_delay=0,
            backoff_factor=1,
            jitter=False,
            on_failure="error",
        )
    ],
)
retry_result = retry_agent.invoke(
    {"messages": [HumanMessage(content="Look up CASE-7.")]}
)
tool_retry_ok = flaky_attempts["count"] == 2 and any(
    isinstance(message, ToolMessage) and "recovered on retry" in str(message.content)
    for message in retry_result["messages"]
)
render_messages(retry_result["messages"])
print(f"TOOL_RETRY_OK {tool_retry_ok}")

# %%
primary_model = LifecycleScriptModel(fail_on_call=True, tool_name=None)
fallback_model = LifecycleScriptModel(
    tool_name=None,
    final_text="The fallback model completed the request.",
)
fallback_agent = create_agent(
    model=primary_model,
    tools=[],
    middleware=[ModelFallbackMiddleware(fallback_model)],
)
fallback_result = fallback_agent.invoke(
    {"messages": [HumanMessage(content="Complete this request safely.")]}
)
model_fallback_ok = (
    fallback_result["messages"][-1].content
    == "The fallback model completed the request."
)
render_messages(fallback_result["messages"])
print(f"MODEL_FALLBACK_OK {model_fallback_ok}")

# %% [markdown]
## Part 5 — Bounds: limit both tool calls and model calls

Limits are guardrails against accidental loops and excessive cost. Tool limits control executions. Model limits control calls to the language model. They protect different resources, so production agents often need both.

# %%
ping_executions = {"count": 0}


@tool
def ping(value: str) -> str:
    """Return a value while counting actual tool executions."""
    ping_executions["count"] += 1
    return value


tool_limit_agent = create_agent(
    model=LifecycleScriptModel(
        tool_name="ping",
        tool_args={"value": "hello"},
        final_text="The tool limit prevented an extra execution.",
        repeat_tool_calls=2,
    ),
    tools=[ping],
    middleware=[ToolCallLimitMiddleware(run_limit=1, exit_behavior="continue")],
)
tool_limit_result = tool_limit_agent.invoke(
    {"messages": [HumanMessage(content="Try to ping twice.")]}
)
tool_limit_enforced = ping_executions["count"] == 1 and any(
    isinstance(message, ToolMessage) and "limit exceeded" in str(message.content).lower()
    for message in tool_limit_result["messages"]
)
render_messages(tool_limit_result["messages"])
print(f"TOOL_LIMIT_ENFORCED {tool_limit_enforced}")

# %%
MODEL_CALL_COUNTS["limited-loop"] = 0
model_limit_agent = create_agent(
    model=LifecycleScriptModel(
        tool_name="ping",
        tool_args={"value": "loop"},
        repeat_tool_calls=99,
        counter_key="limited-loop",
    ),
    tools=[ping],
    middleware=[ModelCallLimitMiddleware(run_limit=2, exit_behavior="end")],
)
model_limit_result = model_limit_agent.invoke(
    {"messages": [HumanMessage(content="Continue calling the tool.")]}
)
model_call_limit_enforced = MODEL_CALL_COUNTS["limited-loop"] == 2 and any(
    isinstance(message, AIMessage) and "model call limits exceeded" in str(message.content).lower()
    for message in model_limit_result["messages"]
)
render_messages(model_limit_result["messages"])
print(f"MODEL_CALL_LIMIT_ENFORCED {model_call_limit_enforced}")

# %% [markdown]
## Part 6 — Protect data with PII middleware

PII means personally identifiable information. This example redacts an email address before it reaches the model. Other supported strategies include blocking, masking, and hashing.

# %%
pii_agent = create_agent(
    model=LifecycleScriptModel(tool_name=None, echo_human=True),
    tools=[],
    middleware=[PIIMiddleware("email", strategy="redact", apply_to_input=True)],
)
pii_result = pii_agent.invoke(
    {"messages": [HumanMessage(content="Please contact alex@example.com tomorrow.")]}
)
pii_text = " ".join(str(message.content) for message in pii_result["messages"])
pii_redacted = "[REDACTED_EMAIL]" in pii_text and "alex@example.com" not in pii_text
render_messages(pii_result["messages"])
print(f"PII_REDACTED {pii_redacted}")

# %% [markdown]
## Part 7 — Manage long histories with summarization middleware

Summarization watches the conversation size. When a configured threshold is reached, it replaces older messages with a generated text summary while retaining recent messages. It manages **model context**; it is not a durable user-memory database.

# %%
summarization_middleware = SummarizationMiddleware(
    model=LifecycleScriptModel(
        tool_name=None,
        final_text="Summary: the user prefers concise explanations.",
    ),
    trigger=("messages", 4),
    keep=("messages", 2),
)
summarization_agent = create_agent(
    model=LifecycleScriptModel(
        tool_name=None,
        final_text="I retained the recent request and an older summary.",
    ),
    tools=[],
    middleware=[summarization_middleware],
)
summarization_result = summarization_agent.invoke(
    {
        "messages": [
            HumanMessage(content="My preferred style is concise."),
            AIMessage(content="Noted."),
            HumanMessage(content="Use examples when helpful."),
            AIMessage(content="Understood."),
            HumanMessage(content="What do you remember?"),
        ]
    }
)
summarization_ok = any(
    isinstance(message, HumanMessage)
    and message.additional_kwargs.get("lc_source") == "summarization"
    for message in summarization_result["messages"]
)
render_messages(summarization_result["messages"])
print(f"SUMMARIZATION_CONFIGURED {summarization_ok}")

# %% [markdown]
## Part 8 — Pause a sensitive tool for human approval

Human-in-the-loop middleware interrupts before a configured tool executes. A checkpointer preserves the paused state. A reviewer may approve, edit, or reject the proposed action.

This notebook uses a fictional in-process message sender. Automatic approval defaults on so the notebook can execute first-to-last. Set `MIDDLEWARE_PRIMER_AUTO_REVIEW=0` to stop after displaying the interrupt payload.

# %%
sent_messages: list[dict[str, str]] = []


@tool
def send_message(recipient: str, subject: str, body: str) -> str:
    """Send one simulated message after human approval."""
    sent_messages.append({"recipient": recipient, "subject": subject, "body": body})
    return json.dumps({"sent": True, "recipient": recipient, "subject": subject})


approval_agent = create_agent(
    model=LifecycleScriptModel(
        tool_name="send_message",
        tool_args={
            "recipient": "reviewer@example.test",
            "subject": "Review request",
            "body": "Please review the attached proposal.",
        },
        final_text="The reviewed message was sent.",
    ),
    tools=[send_message],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "send_message": {
                    "allowed_decisions": ["approve", "edit", "reject"]
                }
            },
            description_prefix="Review this simulated external action",
        )
    ],
    checkpointer=InMemorySaver(),
)
approval_config = {"configurable": {"thread_id": f"middleware-hitl-{uuid4().hex}"}}
approval_pending = approval_agent.invoke(
    {"messages": [HumanMessage(content="Send the review request.")]},
    config=approval_config,
)
hitl_paused = bool(approval_pending.get("__interrupt__")) and sent_messages == []
card(
    "Human review interrupt",
    f"<pre style='white-space:pre-wrap'>{html.escape(str(approval_pending.get('__interrupt__')))}</pre>",
    "#dc2626",
)
print(f"HITL_PAUSED {hitl_paused}")

approval_final = None
if AUTO_REVIEW:
    approval_final = approval_agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=approval_config,
    )
    render_messages(approval_final["messages"])

hitl_approved = AUTO_REVIEW and len(sent_messages) == 1
print(f"HITL_APPROVED {hitl_approved}")

# %% [markdown]
## Part 9 — Optional live-model run

The previous sections always use deterministic model-free execution so their middleware behavior remains reproducible. In an optional provider mode, this section runs the main lifecycle middleware around Ollama Gemma 4 or OpenAI.

The displayed trace contains public messages, tool names, arguments, observations, and the final answer—never hidden chain-of-thought.

# %%
provider_result = None
provider_events: list[dict[str, Any]] = []

if MODE == "model_free":
    print("PROVIDER_RUN skipped mode=model_free")
else:
    if MODE == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for openai mode")
    provider_agent = create_agent(
        model=build_chat_model(MODE),
        tools=[lookup_status],
        system_prompt=(
            "Call lookup_status exactly once for CASE-42. After the tool observation, "
            "answer in one short sentence and do not call another tool."
        ),
        middleware=[LifecycleMiddleware(provider_events)],
    )
    provider_result = provider_agent.invoke(
        {"messages": [HumanMessage(content="What is the status of CASE-42?")]}
    )
    render_messages(provider_result["messages"])
    render_lifecycle(provider_events)
    print(f"PROVIDER_RUN completed mode={MODE}")

# %% [markdown]
## Built-in middleware selection guide

| Situation | Start with |
|---|---|
| A transient read sometimes fails | `ToolRetryMiddleware` with a small retry count |
| A primary model provider is unavailable | `ModelFallbackMiddleware` |
| A loop could overspend | `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` |
| Sensitive text must be removed or blocked | `PIIMiddleware` |
| Old conversation messages exceed context | `SummarizationMiddleware` |
| A tool may create an external effect | `HumanInTheLoopMiddleware` plus a checkpointer |
| One custom hook is required | A decorator such as `@dynamic_prompt` or `@wrap_tool_call` |
| Several hooks share configuration/state | An `AgentMiddleware` subclass |

### Other built-ins worth knowing

| Middleware | Use it for |
|---|---|
| `ToolErrorMiddleware` | Convert selected tool exceptions into controlled observations without retrying automatically |
| `ModelRetryMiddleware` | Retry explicitly transient model failures with a bounded policy |
| `LLMToolSelectorMiddleware` | Reduce a large registered toolbox to a smaller relevant set before the main model call |
| `ContextEditingMiddleware` | Trim or clear older tool results when context grows |
| `TodoListMiddleware` | Give an agent explicit task planning and progress tracking |
| `FilesystemFileSearchMiddleware` | Add bounded file discovery and search capabilities |
| `ShellToolMiddleware` | Expose a shell only when the deployment can isolate and authorize it safely |

### Production cautions

- Retry only operations known to be safe to repeat, or give writes idempotency keys.
- Use hard time and cost budgets in addition to call-count limits.
- Do not expose raw exceptions or credentials in traces.
- Human approval does not replace authentication and authorization.
- Use a durable production checkpointer for pauses that must survive restarts.
- Test middleware order when several wrappers can handle the same exception.

# %% [markdown]
## How these ideas map to the Civil Copilot

The production application uses the same framework boundaries:

| Primer concept | Project implementation |
|---|---|
| Bound model/tool loops | `BoundedRunMiddleware` and registered tool budgets |
| Force observation before the next decision | `SingleToolCallMiddleware` |
| Tool deadlines and controlled failures | `RegistryToolBudgetMiddleware` |
| Bounded transient retry | Structured tool retry middleware |
| Safe error messages | Tool-error redaction middleware |
| Durable agent continuation | PostgreSQL LangGraph checkpoints in local/live modes |

This notebook demonstrates `HumanInTheLoopMiddleware` directly. The main project UI should expose approval only when write-capable tools are intentionally introduced; its current project tools remain read-only.

# %% [markdown]
## Small middleware evaluation suite

These checks validate observable behavior from real `create_agent()` executions. They do not merely check that middleware classes exist.

# %%
evaluation_checks = {
    "lifecycle_order": lifecycle_order_ok,
    "dynamic_prompt_invoked": dynamic_prompt_ok,
    "tool_retry_recovers": tool_retry_ok,
    "model_fallback_recovers": model_fallback_ok,
    "tool_limit_blocks_extra_execution": tool_limit_enforced,
    "model_limit_stops_loop": model_call_limit_enforced,
    "pii_removed_before_model": pii_redacted,
    "summarization_replaces_old_context": summarization_ok,
    "hitl_pauses_before_effect": hitl_paused,
    "hitl_approval_executes_once": hitl_approved,
}
evaluation_pass_rate = sum(evaluation_checks.values()) / len(evaluation_checks)
table([(name, "PASS" if passed else "FAIL") for name, passed in evaluation_checks.items()])
print(f"EVALUATION_PASS_RATE {evaluation_pass_rate:.2f}")

# %% [markdown]
## References

- [LangChain middleware overview](https://docs.langchain.com/oss/python/langchain/middleware/overview)
- [Custom middleware and lifecycle hooks](https://docs.langchain.com/oss/python/langchain/middleware/custom)
- [Built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [Human-in-the-loop middleware](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangChain tools](https://docs.langchain.com/oss/python/langchain/tools)

This notebook prints installed versions at runtime. Middleware APIs evolve, so verify current official documentation and rerun the model-free contracts before copying these patterns.

# %%
assert lifecycle_order_ok is True
assert dynamic_prompt_ok is True
assert tool_retry_ok is True
assert model_fallback_ok is True
assert tool_limit_enforced is True
assert model_call_limit_enforced is True
assert pii_redacted is True
assert summarization_ok is True
assert hitl_paused is True
assert hitl_approved is True
assert evaluation_pass_rate == 1.0

print(
    f"MIDDLEWARE_PRIMER_OK mode={MODE} "
    "create_agent=True lifecycle_hooks=6 builtins=retry_fallback_limits_pii_summary_hitl "
    "secrets_printed=False"
)
'''


def build_notebook() -> nbformat.NotebookNode:
    """Parse percent-cell source into a stable Jupyter notebook."""
    cells: list[nbformat.NotebookNode] = []
    kind: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if kind is None:
            return
        source = "\n".join(buffer).strip("\n")
        if kind == "markdown":
            cells.append(nbformat.v4.new_markdown_cell(source))
        else:
            cells.append(nbformat.v4.new_code_cell(source))
        buffer = []

    for line in SOURCE.splitlines():
        if line == "# %% [markdown]":
            flush()
            kind = "markdown"
        elif line == "# %%":
            flush()
            kind = "code"
        else:
            buffer.append(line)
    flush()

    notebook = nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "middleware_primer": True,
            "domain_neutral": True,
        },
    )
    nbformat.validate(notebook)
    return notebook


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(build_notebook(), TARGET)
    print(f"Wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
