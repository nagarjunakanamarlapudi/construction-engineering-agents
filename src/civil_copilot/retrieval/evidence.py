"""Evidence packet returned by retrieval and consumed by answers and agents."""

from typing import Literal

from pydantic import BaseModel, Field

from civil_copilot.data.models import DocumentChunk


class RerankerScoreTrace(BaseModel):
    """One validated model score for an existing fused candidate."""

    candidate_id: str
    score: float


class RerankerTrace(BaseModel):
    """Safe, secret-free description of the second-stage ranking decision."""

    provider: str
    model: str
    version: str
    status: Literal["success", "fallback", "failed"]
    failure_policy: str
    candidate_count: int = 0
    input_candidate_ids: list[str] = Field(default_factory=list)
    scores: list[RerankerScoreTrace] = Field(default_factory=list)
    ignored_candidate_ids: list[str] = Field(default_factory=list)
    error_type: str | None = None
    attempted_provider: str | None = None
    attempted_model: str | None = None
    attempted_version: str | None = None


class RetrievalTrace(BaseModel):
    keyword_candidates: int = 0
    vector_candidates: int = 0
    fused_candidates: int = 0
    filtered_candidates: int = 0
    returned_evidence: int = 0
    exact_identifiers: list[str] = Field(default_factory=list)
    hybrid_ranking: list[str] = Field(default_factory=list)
    reranked_ranking: list[str] = Field(default_factory=list)
    reranker: RerankerTrace | None = None


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


class HybridCandidate(BaseModel):
    """One Qdrant-backed candidate with transparent per-signal ranks."""

    chunk: DocumentChunk
    fused_score: float
    exact_rank: int | None = None
    text_rank: int | None = None
    dense_rank: int | None = None
