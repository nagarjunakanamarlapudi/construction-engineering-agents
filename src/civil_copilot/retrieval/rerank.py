"""Transparent deterministic reranking for identifiers, revisions, and lexical agreement."""

from __future__ import annotations

import re

from civil_copilot.data.models import DocumentChunk

TOKEN = re.compile(r"[a-z0-9]+")
IDENTIFIER = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b", re.IGNORECASE)


def extract_identifiers(text: str) -> list[str]:
    return sorted({match.group(0).upper() for match in IDENTIFIER.finditer(text)})


def rerank_score(
    question: str, chunk: DocumentChunk, fused_score: float
) -> tuple[float, list[str]]:
    score = fused_score
    reasons: list[str] = []
    question_upper = question.upper()
    if chunk.record_id.upper() in question_upper:
        score += 2.0
        reasons.append("exact record identifier")
    for identifier in extract_identifiers(question):
        if identifier in chunk.text.upper() and identifier != chunk.record_id.upper():
            score += 0.25
            reasons.append(f"mentions {identifier}")
    question_tokens = set(TOKEN.findall(question.lower()))
    chunk_tokens = set(TOKEN.findall(chunk.text.lower()))
    overlap = len(question_tokens & chunk_tokens) / max(len(question_tokens), 1)
    score += 0.2 * overlap
    if overlap:
        reasons.append("question term overlap")
    if overlap or chunk.record_id.upper() in question_upper:
        if str(chunk.metadata.get("status", "")).lower() in {
            "current",
            "approved",
            "accepted",
            "closed",
        }:
            score += 0.15
            reasons.append("current or accepted status")
        if str(chunk.metadata.get("status", "")).lower() in {"superseded", "void"}:
            score -= 0.2
            reasons.append("superseded revision")
    return score, reasons
