"""Langfuse configuration with recursive secret and oversized-text redaction."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from langfuse import Langfuse

from civil_copilot.config import Settings

SENSITIVE_KEY_PARTS = ("key", "secret", "password", "authorization", "token", "credential")


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
    return TracingBundle(enabled=True, client=client)
