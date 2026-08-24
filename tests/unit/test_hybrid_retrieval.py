import pytest

from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from civil_copilot.retrieval.query import QueryContext


def _chunk(chunk_id: str, record_id: str, text: str, **metadata: object) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        record_id=record_id,
        project_id="BLR-STEEL-DEMO",
        text=text,
        ordinal=0,
        data_origin="synthetic_academic_demo",
        source_path=f"data/demo#{record_id}",
        access_scopes=["project:blr-steel-demo"],
        metadata={"status": "current", **metadata},
    )


def test_reciprocal_rank_fusion_matches_hand_derived_order():
    scores = reciprocal_rank_fusion(
        keyword_ids=["A", "B", "C"],
        vector_ids=["B", "C", "D"],
        rank_constant=10,
    )

    assert list(scores) == ["B", "C", "A", "D"]
    assert scores["B"] > scores["C"] > scores["A"] > scores["D"]


def test_reciprocal_rank_fusion_counts_exact_identifier_as_its_own_signal():
    scores = reciprocal_rank_fusion(
        keyword_ids=["B", "C", "A"],
        vector_ids=["B", "A", "C"],
        exact_ids=["A"],
        rank_constant=10,
    )

    assert list(scores)[0] == "A"
    assert scores["A"] == pytest.approx(1 / 11 + 1 / 13 + 1 / 12)


def test_hybrid_retriever_boosts_exact_ids_filters_access_and_reranks_current_revision():
    chunks = [
        _chunk("old", "RFI-087", "RFI-087 old response on drawing S-204", status="superseded"),
        _chunk("new", "RFI-087", "RFI-087 approved response incorporated in S-204 Rev 5"),
        _chunk("semantic", "RFI-090", "Connection clarification incorporated into a revised plan"),
        _chunk("restricted", "RFI-087-PRIVATE", "RFI-087 confidential commercial note").model_copy(
            update={"access_scopes": ["restricted:commercial"]},
        ),
    ]

    def vector_search(_query: str, _limit: int) -> list[tuple[str, float]]:
        return [("semantic", 0.95), ("new", 0.80), ("restricted", 0.99), ("old", 0.75)]

    packet = HybridRetriever(chunks, vector_search).retrieve(
        QueryContext(
            question="What did RFI-087 change in S-204 Rev 5?",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            top_k=3,
        )
    )

    assert packet.evidence[0].chunk.chunk_id == "new"
    assert "restricted" not in {item.chunk.chunk_id for item in packet.evidence}
    assert packet.evidence[0].exact_id_match is True
    assert packet.evidence[0].rerank_score > packet.evidence[-1].rerank_score
    assert packet.retrieval_trace.keyword_candidates > 0
    assert packet.retrieval_trace.vector_candidates == 4
    assert packet.retrieval_trace.reranker is not None
    assert packet.retrieval_trace.reranker.provider == "deterministic"
    assert packet.retrieval_trace.reranker.model == "exact_lexical_revision_heuristic"
    assert packet.retrieval_trace.reranked_ranking[0] == "RFI-087"
    assert packet.retrieval_trace.reranked_ranking.count("RFI-087") == 1
