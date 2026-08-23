"""Grounded answer construction with explicit citations and safe abstention."""

from __future__ import annotations

from pydantic import BaseModel, Field

from civil_copilot.retrieval.evidence import EvidencePacket


class Citation(BaseModel):
    record_id: str
    chunk_id: str
    title: str
    source_path: str
    source_url: str | None = None
    data_origin: str


class AnswerResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    grounded: bool
    abstained: bool
    unsupported_claims: list[str] = Field(default_factory=list)


class GroundedAnswerService:
    """Create a concise extractive answer; an LLM-backed mode can replace only this layer."""

    def answer(self, packet: EvidencePacket, *, max_statements: int = 4) -> AnswerResult:
        if not packet.evidence:
            return AnswerResult(
                answer=(
                    "I do not have enough evidence in the permitted project sources to answer "
                    "this question."
                ),
                grounded=True,
                abstained=True,
            )

        citations: list[Citation] = []
        statements: list[str] = []
        seen_records: set[str] = set()
        for item in packet.evidence[:max_statements]:
            chunk = item.chunk
            if chunk.record_id in seen_records:
                continue
            seen_records.add(chunk.record_id)
            citations.append(
                Citation(
                    record_id=chunk.record_id,
                    chunk_id=chunk.chunk_id,
                    title=chunk.text.split(".", 1)[0],
                    source_path=chunk.source_path,
                    source_url=chunk.source_url,
                    data_origin=chunk.data_origin,
                )
            )
            source = chunk.source_url or (
                f"http://127.0.0.1:8001/api/records/{chunk.record_id}"
            )
            excerpt = chunk.text.strip()
            if len(excerpt) > 360:
                excerpt = excerpt[:357].rsplit(" ", 1)[0] + "…"
            statements.append(f"{excerpt} [{chunk.record_id}]({source})")

        return AnswerResult(
            answer="\n\n".join(statements),
            citations=citations,
            grounded=True,
            abstained=False,
            unsupported_claims=[],
        )
