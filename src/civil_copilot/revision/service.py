"""Deterministic, evidence-preserving comparison of two controlled revisions."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, Field

from civil_copilot.data.models import ProjectRecord

WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class RevisionComparison(BaseModel):
    document_id: str
    from_record_id: str
    to_record_id: str
    from_revision: str
    to_revision: str
    status_change: dict[str, str]
    effective_date_change: dict[str, str]
    metadata_changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    added_terms: list[str] = Field(default_factory=list)
    removed_terms: list[str] = Field(default_factory=list)
    content_similarity: float = Field(ge=0.0, le=1.0)
    summary: str


def _tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


def compare_revision_records(
    records: list[ProjectRecord],
    *,
    document_id: str,
    from_revision: str,
    to_revision: str,
) -> RevisionComparison:
    """Compare two specifically named, permitted revisions without asking an LLM."""

    matching = {
        str(record.revision): record
        for record in records
        if record.record_type == "drawing"
        and str(record.metadata.get("document_number")) == document_id
        and str(record.revision) in {from_revision, to_revision}
    }
    if set(matching) != {from_revision, to_revision}:
        raise ValueError("both requested revisions are required for a controlled comparison")

    older = matching[from_revision]
    newer = matching[to_revision]
    older_tokens = _tokens(f"{older.title} {older.content}")
    newer_tokens = _tokens(f"{newer.title} {newer.content}")
    added = sorted(set(newer_tokens) - set(older_tokens))[:40]
    removed = sorted(set(older_tokens) - set(newer_tokens))[:40]
    metadata_changes = {
        key: {"from": older.metadata.get(key), "to": newer.metadata.get(key)}
        for key in sorted(set(older.metadata) | set(newer.metadata))
        if older.metadata.get(key) != newer.metadata.get(key)
    }
    similarity = SequenceMatcher(a=older_tokens, b=newer_tokens, autojunk=False).ratio()
    summary = (
        f"{document_id} changed from revision {from_revision} to revision {to_revision}. "
        f"Its control status changed from {older.status} to {newer.status}; "
        f"{len(added)} terms were added and {len(removed)} terms were removed."
    )
    return RevisionComparison(
        document_id=document_id,
        from_record_id=older.record_id,
        to_record_id=newer.record_id,
        from_revision=from_revision,
        to_revision=to_revision,
        status_change={"from": older.status, "to": newer.status},
        effective_date_change={
            "from": older.effective_date.isoformat(),
            "to": newer.effective_date.isoformat(),
        },
        metadata_changes=metadata_changes,
        added_terms=added,
        removed_terms=removed,
        content_similarity=round(similarity, 4),
        summary=summary,
    )
