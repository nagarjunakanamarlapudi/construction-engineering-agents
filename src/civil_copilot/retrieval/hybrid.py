"""Keyword plus semantic retrieval with rank fusion, filters, and reranking."""

from __future__ import annotations

import re
from collections.abc import Callable

from rank_bm25 import BM25Okapi

from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.evidence import EvidenceItem, EvidencePacket, RetrievalTrace
from civil_copilot.retrieval.query import QueryContext
from civil_copilot.retrieval.rerank import extract_identifiers, rerank_score

TOKEN = re.compile(r"[a-z0-9-]+")
VectorSearch = Callable[[str, int], list[tuple[str, float]]]


def reciprocal_rank_fusion(
    keyword_ids: list[str],
    vector_ids: list[str],
    rank_constant: int = 60,
) -> dict[str, float]:
    """Combine two rankings without pretending their raw scores share a scale."""

    scores: dict[str, float] = {}
    for ranking in (keyword_ids, vector_ids):
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (rank_constant + rank)
    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0])))


class HybridRetriever:
    def __init__(self, chunks: list[DocumentChunk], vector_search: VectorSearch) -> None:
        self.chunks = chunks
        self.vector_search = vector_search

    @staticmethod
    def _eligible(chunk: DocumentChunk, context: QueryContext) -> bool:
        permitted = bool(set(chunk.access_scopes) & set(context.access_scopes))
        correct_project = chunk.project_id in {context.project_id, "PUBLIC-REFERENCE"}
        metadata_match = all(
            chunk.metadata.get(key) == value for key, value in context.filters.items()
        )
        return permitted and correct_project and metadata_match

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

    def retrieve(self, context: QueryContext) -> EvidencePacket:
        eligible = [chunk for chunk in self.chunks if self._eligible(chunk, context)]
        by_id = {chunk.chunk_id: chunk for chunk in eligible}
        keyword_ids = self._keyword_ranking(context.question, eligible)
        vector_results = self.vector_search(context.question, max(context.top_k * 4, 20))
        vector_ids = [chunk_id for chunk_id, _score in vector_results]
        eligible_vector_ids = [chunk_id for chunk_id in vector_ids if chunk_id in by_id]
        fused = reciprocal_rank_fusion(keyword_ids, eligible_vector_ids)

        evidence: list[EvidenceItem] = []
        for chunk_id, fused_score in fused.items():
            chunk = by_id.get(chunk_id)
            if not chunk:
                continue
            score, reasons = rerank_score(context.question, chunk, fused_score)
            exact = chunk.record_id.upper() in context.question.upper()
            evidence.append(
                EvidenceItem(
                    chunk=chunk,
                    fused_score=fused_score,
                    rerank_score=score,
                    exact_id_match=exact,
                    reasons=reasons,
                )
            )
        evidence.sort(key=lambda item: (-item.rerank_score, item.chunk.chunk_id))
        returned = [item for item in evidence if item.rerank_score >= context.minimum_rerank_score][
            : context.top_k
        ]
        return EvidencePacket(
            question=context.question,
            evidence=returned,
            retrieval_trace=RetrievalTrace(
                keyword_candidates=len(keyword_ids),
                vector_candidates=len(vector_results),
                fused_candidates=len(fused),
                filtered_candidates=len(eligible),
                returned_evidence=len(returned),
                exact_identifiers=extract_identifiers(context.question),
            ),
        )
