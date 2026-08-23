"""Portable offline composition used by tests, notebooks, and the API fallback."""

from __future__ import annotations

from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.data.models import Corpus
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.stores.qdrant import DeterministicEmbedding


def build_offline_workflow(corpus: Corpus) -> CopilotWorkflow:
    embedding = DeterministicEmbedding()
    vectors = {chunk.chunk_id: embedding.embed_query(chunk.text) for chunk in corpus.chunks}

    def vector_search(query: str, limit: int) -> list[tuple[str, float]]:
        query_vector = embedding.embed_query(query)
        scores = [
            (
                chunk_id,
                sum(left * right for left, right in zip(query_vector, vector, strict=True)),
            )
            for chunk_id, vector in vectors.items()
        ]
        return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]

    return CopilotWorkflow(
        ProjectTools(
            corpus.records,
            HybridRetriever(corpus.chunks, vector_search),
            ProjectGraphService(corpus.records, corpus.relationships),
        )
    )
