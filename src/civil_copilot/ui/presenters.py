"""Convert API records into concise, reader-facing UI content."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnswerPresentation:
    finding: str
    explanation: str
    connections: tuple[str, ...]
    source_count: int
    grounded: bool
    abstained: bool


@dataclass(frozen=True)
class RevisionPreview:
    record_id: str
    revision: str
    status: str
    effective_date: str
    summary: str


@dataclass(frozen=True)
class StandardMatrixRow:
    topic: str
    status: str
    reason: str
    project_sources: tuple[str, ...]
    official_source: str


_SOURCE_LINK = re.compile(r"\s*\[[^\]]+\]\([^)]+\)\s*$")
_RECORD_HEADER = re.compile(r"^[^.]+\.\s+Record\s+[^.]+\.\s*", re.IGNORECASE)
_RECORD_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
_ORIGIN_PREFIX = re.compile(
    r"^(?:SYNTHETIC\s+—\s+ACADEMIC\s+DEMO|OFFICIAL\s+PUBLIC\s+PREVIEW)[:.]?\s*",
    re.IGNORECASE,
)
_ORIGIN_MARKERS = (
    "SYNTHETIC — ACADEMIC DEMO.",
    "OFFICIAL PUBLIC PREVIEW.",
    "Official public preview.",
)
_RELATIONSHIP_PHRASES = {
    "AFFECTS": "affects",
    "CHANGES_OR_CLARIFIES": "changes or clarifies",
    "DEPENDS_ON": "depends on",
    "DELIVERS": "delivers",
    "INSTALLED_BY": "is installed by",
    "RAISED_NCR": "raised",
    "REQUIRES": "requires",
    "RESOLVES": "resolves",
    "SUPERSEDES": "supersedes",
}
_CAUSE_TERMS = (
    "approved response",
    "clarification",
    "required",
    "pending",
    "reinspection",
    "rejected",
    "blocked",
)


def normalize_scenarios(payload: Any) -> list[dict[str, Any]]:
    """Return only API scenario objects that the UI can render safely."""

    if not isinstance(payload, list):
        return []
    return [
        dict(scenario)
        for scenario in payload
        if isinstance(scenario, Mapping)
        and isinstance(scenario.get("scenario_id"), str)
        and bool(scenario["scenario_id"])
        and isinstance(scenario.get("question"), str)
        and bool(scenario["question"])
    ]


def clean_indexed_text(value: str) -> str:
    """Remove ingestion-only headers and trailing source links from a passage."""

    text = value.strip()
    for marker in _ORIGIN_MARKERS:
        if marker in text:
            text = text.rsplit(marker, 1)[1].strip()
            break
    text = _RECORD_HEADER.sub("", text)
    text = _ORIGIN_PREFIX.sub("", text)
    text = _SOURCE_LINK.sub("", text)
    return text.strip()


def route_label(route: str) -> str:
    return {
        "rag": "RAG",
        "graph_rag": "Graph RAG",
        "agentic_rag": "Agentic RAG",
    }.get(route, route.replace("_", " ").title())


def humanize_token(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _plain_connections(paths: list[Mapping[str, Any]], anchors: set[str]) -> tuple[str, ...]:
    connections: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        for edge in path.get("edges", []):
            source_id = str(edge.get("source_id", "")).strip()
            target_id = str(edge.get("target_id", "")).strip()
            relationship = str(edge.get("relationship_type", "")).strip()
            key = (source_id, relationship, target_id)
            if not all(key) or key in seen:
                continue
            if anchors and source_id not in anchors and target_id not in anchors:
                continue
            seen.add(key)
            phrase = _RELATIONSHIP_PHRASES.get(relationship, relationship.replace("_", " ").lower())
            connections.append(f"{source_id} {phrase} {target_id}.")
            if len(connections) == 6:
                return tuple(connections)
    return tuple(connections)


def _impact_headline(anchors: list[str], connections: tuple[str, ...]) -> str | None:
    if not anchors:
        return None
    anchor = anchors[0]
    clauses = [
        connection.removeprefix(f"{anchor} ").removesuffix(".")
        for connection in connections
        if connection.startswith(f"{anchor} ")
    ]
    if not clauses:
        return None
    clauses.sort(key=lambda value: (not value.startswith("affects "), value))
    if len(clauses) == 1:
        joined = clauses[0]
    else:
        joined = ", ".join(clauses[:-1]) + f" and {clauses[-1]}"
    return f"{anchor} directly {joined}."


def _intent_first_answer(
    question: str, passages: list[str], connections: tuple[str, ...]
) -> tuple[str, str]:
    if not passages:
        return "No answer was returned.", ""

    lowered_question = question.lower()
    named_records = _RECORD_ID.findall(question)
    if "blocked" in lowered_question:
        cause = next(
            (
                passage
                for passage in passages[1:]
                if any(term in passage.lower() for term in _CAUSE_TERMS)
            ),
            None,
        )
        if cause:
            activity = next(
                (record_id for record_id in named_records if record_id.startswith("ACT-")),
                "The activity",
            )
            finding = f"{activity} was blocked pending the clarification described in the evidence."
            return finding, cause

    if "impact" in lowered_question or "downstream" in lowered_question:
        headline = _impact_headline(named_records, connections)
        if headline:
            return headline, " ".join(passages)

    return passages[0], " ".join(passages[1:])


def build_answer_presentation(response: Mapping[str, Any]) -> AnswerPresentation:
    question = str(response.get("question", ""))
    passages = [
        cleaned
        for passage in re.split(r"\n\s*\n", str(response.get("answer", "")))
        if (cleaned := clean_indexed_text(passage))
    ]
    anchors = set(_RECORD_ID.findall(question))
    connections = _plain_connections(list(response.get("graph_paths", [])), anchors)
    finding, explanation = _intent_first_answer(question, passages, connections)
    return AnswerPresentation(
        finding=finding,
        explanation=explanation,
        connections=connections,
        source_count=len(response.get("citations", [])),
        grounded=bool(response.get("grounded")),
        abstained=bool(response.get("abstained")),
    )


def build_revision_preview(revision: Mapping[str, Any]) -> RevisionPreview:
    return RevisionPreview(
        record_id=str(revision.get("record_id", "")),
        revision=str(revision.get("revision", "")),
        status=humanize_token(str(revision.get("status", ""))),
        effective_date=str(revision.get("effective_date", "")),
        summary=clean_indexed_text(str(revision.get("content", ""))),
    )


def build_standard_matrix_rows(report: Mapping[str, Any]) -> list[StandardMatrixRow]:
    """Keep the evidence matrix readable while preserving both provenance classes."""

    rows: list[StandardMatrixRow] = []
    for raw in report.get("rows", []):
        if not isinstance(raw, Mapping):
            continue
        project_evidence = raw.get("project_evidence", [])
        official = raw.get("official_source", {})
        rows.append(
            StandardMatrixRow(
                topic=str(raw.get("topic", "")),
                status=str(raw.get("status", "")),
                reason=str(raw.get("reason", "")),
                project_sources=tuple(
                    str(item.get("record_id", ""))
                    for item in project_evidence
                    if isinstance(item, Mapping) and item.get("record_id")
                ),
                official_source=(
                    " · ".join(
                        str(official.get(field, ""))
                        for field in ("record_id", "chunk_id")
                        if official.get(field)
                    )
                    if isinstance(official, Mapping)
                    else ""
                ),
            )
        )
    return rows
