"""Explicit transient retry policy shared by agent middleware and deadline proofs."""

from __future__ import annotations

TRANSIENT_TOOL_MAX_RETRIES = 1
HARD_DEADLINE_TOOL_NAMES = ("search_documents",)
TRANSIENT_RETRY_TOOL_NAMES = (
    "get_record",
    "query_project_graph",
    "analyze_schedule",
    "compare_revisions",
    "calculate",
)


def tool_attempt_count(tool_name: str) -> int:
    """Return the maximum middleware attempts for a registered tool call."""

    if tool_name in TRANSIENT_RETRY_TOOL_NAMES:
        return TRANSIENT_TOOL_MAX_RETRIES + 1
    return 1
