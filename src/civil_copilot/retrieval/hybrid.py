"""Keyword plus semantic retrieval with rank fusion, filters, and reranking."""

from __future__ import annotations

import re
from collections.abc import Callable

from rank_bm25 import BM25Okapi

from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.evidence import EvidencePacket, HybridCandidate, RetrievalTrace
from civil_copilot.retrieval.query import QueryContext
from civil_copilot.retrieval.rerank import (
    DeterministicHeuristicReranker,
    Reranker,
    extract_identifiers,
)

TOKEN = re.compile(r"[a-z0-9-]+")
VectorSearch = Callable[[str, int], list[tuple[str, float]]]


def reciprocal_rank_fusion(
    keyword_ids: list[str],
    vector_ids: list[str],
    rank_constant: int = 60,
    *,
    exact_ids: list[str] | None = None,
) -> dict[str, float]:
    """Combine two rankings without pretending their raw scores share a scale."""

    scores: dict[str, float] = {}
    for ranking in (exact_ids or [], keyword_ids, vector_ids):
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (rank_constant + rank)
    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0])))


class HybridRetriever:
    def __init__(
        self,
        chunks: list[DocumentChunk],
        vector_search: VectorSearch,
        *,
        reranker: Reranker | None = None,
    ) -> None:
        self.chunks = chunks
        self.vector_search = vector_search
        self.reranker = reranker or DeterministicHeuristicReranker()

    @staticmethod
    def _eligible(chunk: DocumentChunk, context: QueryContext) -> bool:
        permitted = bool(set(chunk.access_scopes) & set(context.access_scopes))
        correct_project = chunk.project_id in {context.project_id, "PUBLIC-REFERENCE"}
        metadata_match = all(
            chunk.metadata.get(key) == value for key, value in context.filters.items()
        )
        effective_date = chunk.effective_date
        temporal_match = (
            context.as_of_date is None
            or effective_date is None
            or effective_date <= context.as_of_date
        )
        return permitted and correct_project and metadata_match and temporal_match

    def _keyword_ranking(self, question: str, chunks: list[DocumentChunk]) -> list[str]:
        if not chunks:
            return []
        tokenized = [TOKEN.findall(chunk.text.lower()) for chunk in chunks]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(TOKEN.findall(question.lower()))
        ranked = sorted(
            zip(chunks, scores, strict=True), key=lambda item: (-item[1], item[0].chunk_id)
        )
        return [chunk.chunk_id for chunk, score in ranked if score > 0]

    def search_candidates(
        self, context: QueryContext
    ) -> tuple[list[HybridCandidate], int, int, int]:
        """Return fused, permission-filtered candidates without second-stage reranking."""

        eligible = [chunk for chunk in self.chunks if self._eligible(chunk, context)]
        by_id = {chunk.chunk_id: chunk for chunk in eligible}
        keyword_ids = self._keyword_ranking(context.question, eligible)
        vector_results = self.vector_search(context.question, max(context.top_k * 4, 20))
        vector_ids = [chunk_id for chunk_id, _score in vector_results]
        eligible_vector_ids = [chunk_id for chunk_id in vector_ids if chunk_id in by_id]
        identifiers = set(extract_identifiers(context.question))
        exact_ids = [
            chunk.chunk_id
            for chunk in sorted(eligible, key=lambda item: item.chunk_id)
            if chunk.record_id.upper() in identifiers
        ]
        fused = reciprocal_rank_fusion(
            keyword_ids,
            eligible_vector_ids,
            exact_ids=exact_ids,
        )
        exact_ranks = {chunk_id: rank for rank, chunk_id in enumerate(exact_ids, start=1)}
        text_ranks = {chunk_id: rank for rank, chunk_id in enumerate(keyword_ids, start=1)}
        dense_ranks = {chunk_id: rank for rank, chunk_id in enumerate(eligible_vector_ids, start=1)}
        candidates: list[HybridCandidate] = []
        for chunk_id, fused_score in fused.items():
            chunk = by_id.get(chunk_id)
            if not chunk:
                continue
            candidates.append(
                HybridCandidate(
                    chunk=chunk,
                    fused_score=fused_score,
                    exact_rank=exact_ranks.get(chunk_id),
                    text_rank=text_ranks.get(chunk_id),
                    dense_rank=dense_ranks.get(chunk_id),
                )
            )
        candidates.sort(key=lambda item: (-item.fused_score, item.chunk.chunk_id))
        return candidates, len(keyword_ids), len(vector_results), len(eligible)

    def retrieve(self, context: QueryContext) -> EvidencePacket:
        candidates, keyword_count, vector_count, eligible_count = self.search_candidates(context)
        outcome = self.reranker.rerank(context.question, candidates)
        evidence = outcome.evidence
        considered_ids = set(outcome.trace.input_candidate_ids)
        returned = [item for item in evidence if item.rerank_score >= context.minimum_rerank_score][
            : context.top_k
        ]
        return EvidencePacket(
            question=context.question,
            evidence=returned,
            retrieval_trace=RetrievalTrace(
                keyword_candidates=keyword_count,
                vector_candidates=vector_count,
                fused_candidates=len(candidates),
                filtered_candidates=eligible_count,
                returned_evidence=len(returned),
                exact_identifiers=extract_identifiers(context.question),
                hybrid_ranking=list(
                    dict.fromkeys(
                        item.chunk.record_id
                        for item in candidates
                        if item.chunk.chunk_id in considered_ids
                    )
                ),
                reranked_ranking=list(dict.fromkeys(item.chunk.record_id for item in evidence)),
                reranker=outcome.trace,
            ),
        )
