"""Langfuse configuration with recursive secret and oversized-text redaction."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from pydantic import BaseModel

from civil_copilot.config import Settings

SENSITIVE_KEY_PARTS = ("key", "secret", "password", "authorization", "token", "credential")


class TraceReference(BaseModel):
    """Safe public pointer to a trace without exposing trace payloads or credentials."""

    provider: Literal["none", "local", "langfuse"] = "none"
    trace_id: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class TracingRun:
    callbacks: tuple[Any, ...]
    reference: TraceReference


def redact_trace_payload(
    value: Any = None,
    *,
    data: Any = None,
    max_text_length: int = 1200,
) -> Any:
    """Redact trace data, including Langfuse's ``mask(data=...)`` callback form."""
    if data is not None:
        value = data
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_trace_payload(item, max_text_length=max_text_length)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_trace_payload(item, max_text_length=max_text_length) for item in value]
    if isinstance(value, str) and len(value) > max_text_length:
        return value[:max_text_length] + "… [TRUNCATED]"
    return value


@dataclass
class TracingBundle:
    enabled: bool
    client: Langfuse | None = None
    callback_handler: Any | None = None
    callback_factory: Callable[[dict[str, str]], Any] | None = None
    _active_run: ContextVar[TracingRun | None] = field(
        default_factory=lambda: ContextVar("civil_copilot_active_trace_run", default=None),
        repr=False,
    )

    def callbacks(self) -> tuple[Any, ...]:
        active = self._active_run.get()
        if active is not None:
            return active.callbacks
        return (self.callback_handler,) if self.callback_handler is not None else ()

    def flush(self) -> None:
        if self.client:
            self.client.flush()

    def span(self, name: str, input_payload: Any = None):
        if not self.client:
            return nullcontext(None)
        return self.client.start_as_current_span(
            name=name,
            input=redact_trace_payload(input_payload),
        )

    def reference(self, trace_id: str | None = None) -> TraceReference:
        return TraceReference(trace_id=trace_id)

    @contextmanager
    def run(self, name: str, input_payload: Any = None) -> Iterator[TracingRun]:
        """Create one real run boundary and expose only its safe public reference."""

        if not self.client:
            active = TracingRun(
                callbacks=(),
                reference=TraceReference(
                    provider="local",
                    trace_id=f"local-run-{uuid4()}",
                ),
            )
            token = self._active_run.set(active)
            try:
                yield active
            finally:
                self._active_run.reset(token)
            return

        trace_id = self.client.create_trace_id()
        trace_context = {"trace_id": trace_id}
        callback = (
            self.callback_factory(trace_context)
            if self.callback_factory is not None
            else self.callback_handler
        )
        reference = TraceReference(
            provider="langfuse",
            trace_id=trace_id,
            url=self.client.get_trace_url(trace_id=trace_id),
        )
        active = TracingRun(
            callbacks=(callback,) if callback is not None else (),
            reference=reference,
        )
        token = self._active_run.set(active)
        try:
            with self.client.start_as_current_span(
                trace_context=trace_context,
                name=name,
                input=redact_trace_payload(input_payload),
            ):
                yield active
        finally:
            self._active_run.reset(token)


def create_tracing(settings: Settings) -> TracingBundle:
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return TracingBundle(enabled=False)
    client = Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=str(settings.langfuse_base_url).rstrip("/"),
        environment=settings.app_env,
        debug=settings.langfuse_debug,
        mask=redact_trace_payload,
    )
    return TracingBundle(
        enabled=True,
        client=client,
        callback_handler=CallbackHandler(
            public_key=settings.langfuse_public_key.get_secret_value(),
            update_trace=True,
        ),
        callback_factory=lambda trace_context: CallbackHandler(
            public_key=settings.langfuse_public_key.get_secret_value(),
            update_trace=True,
            trace_context=trace_context,
        ),
    )
