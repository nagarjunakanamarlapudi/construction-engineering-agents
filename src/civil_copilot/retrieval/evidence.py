"""Evidence packet returned by retrieval and consumed by answers and agents."""

from pydantic import BaseModel, Field

from civil_copilot.data.models import DocumentChunk


class RetrievalTrace(BaseModel):
    keyword_candidates: int = 0
    vector_candidates: int = 0
    fused_candidates: int = 0
    filtered_candidates: int = 0
    returned_evidence: int = 0
    exact_identifiers: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    chunk: DocumentChunk
    fused_score: float
    rerank_score: float
    exact_id_match: bool = False
    reasons: list[str] = Field(default_factory=list)


class EvidencePacket(BaseModel):
    question: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    retrieval_trace: RetrievalTrace
