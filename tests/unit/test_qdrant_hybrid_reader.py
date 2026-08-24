from datetime import date
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.rerank import extract_identifiers
from civil_copilot.stores.qdrant import DeterministicEmbedding, QdrantSearchStore


def _chunk(
    chunk_id: str,
    record_id: str,
    text: str,
    *,
    project_id: str = "PROJECT-1",
    access_scopes: list[str] | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        record_id=record_id,
        project_id=project_id,
        text=text,
        ordinal=0,
        data_origin="synthetic_academic_demo",
        source_path=f"data/test#{record_id}",
        access_scopes=access_scopes or ["role:engineer"],
        metadata={"status": "current", "discipline": "structural"},
    )


def test_qdrant_hybrid_reader_filters_before_ranking_and_reports_each_signal_rank():
    store = QdrantSearchStore.__new__(QdrantSearchStore)
    store.client = QdrantClient(location=":memory:")
    store.embedding = DeterministicEmbedding()
    store.collection_name = "task_1_hybrid_reader"
    store.initialize()
    store.upsert_chunks(
        [
            _chunk(
                "visible-exact",
                "RFI-087",
                "RFI-087 approved the revised structural connection plate.",
            ),
            _chunk(
                "visible-semantic",
                "RFI-090",
                "The approved clarification revised the beam connection detail.",
            ),
            _chunk(
                "restricted",
                "RFI-087-PRIVATE",
                "RFI-087 confidential commercial analysis.",
                access_scopes=["role:commercial"],
            ),
            _chunk(
                "other-project",
                "RFI-087-OTHER",
                "RFI-087 belongs to a different project.",
                project_id="PROJECT-2",
            ),
        ]
    )

    search_hybrid = getattr(store, "search_hybrid", lambda **_kwargs: [])
    candidates = search_hybrid(
        query="What did RFI-087 approve about the connection?",
        project_id="PROJECT-1",
        access_scopes=["role:engineer"],
        metadata_filters={"status": "current", "discipline": "structural"},
        limit=10,
    )

    assert candidates[0].chunk.record_id == "RFI-087"
    assert candidates[0].exact_rank == 1
    assert candidates[0].text_rank is not None
    assert candidates[0].dense_rank is not None
    assert {candidate.chunk.chunk_id for candidate in candidates} <= {
        "visible-exact",
        "visible-semantic",
    }


def test_exact_identifier_extraction_includes_single_letter_drawing_prefixes():
    assert extract_identifiers("Compare S-204 Rev 3 with S-204 Rev 5") == ["S-204"]


def test_qdrant_as_of_keeps_shipped_legacy_chunks_with_unknown_effective_date():
    corpus = load_corpus(Path(__file__).parents[2])
    shipped_rfi_chunks = [chunk for chunk in corpus.chunks if chunk.record_id == "RFI-087"]
    assert shipped_rfi_chunks
    assert all(chunk.effective_date is None for chunk in shipped_rfi_chunks)

    store = QdrantSearchStore.__new__(QdrantSearchStore)
    store.client = QdrantClient(location=":memory:")
    store.embedding = DeterministicEmbedding()
    store.collection_name = "task_1_legacy_as_of"
    store.initialize()
    store.upsert_chunks(shipped_rfi_chunks)

    candidates = store.search_hybrid(
        query="What did RFI-087 approve?",
        project_id="BLR-STEEL-DEMO",
        access_scopes=["project:blr-steel-demo"],
        as_of_date=date(2026, 6, 1),
        limit=5,
    )

    assert [candidate.chunk.record_id for candidate in candidates] == ["RFI-087"]


@pytest.mark.parametrize("first_dimension,second_dimension", [(128, 1536), (1536, 128)])
def test_qdrant_rejects_incompatible_existing_dense_dimension_in_both_orders(
    first_dimension: int,
    second_dimension: int,
):
    class DimensionOnlyEmbedding:
        def __init__(self, dimension: int) -> None:
            self.dimension = dimension

    client = QdrantClient(location=":memory:")
    first = QdrantSearchStore.__new__(QdrantSearchStore)
    first.client = client
    first.embedding = DimensionOnlyEmbedding(first_dimension)
    first.collection_name = "task_5_schema_boundary"
    first.initialize()

    second = QdrantSearchStore.__new__(QdrantSearchStore)
    second.client = client
    second.embedding = DimensionOnlyEmbedding(second_dimension)
    second.collection_name = first.collection_name

    with pytest.raises(ValueError, match="incompatible.*reindex"):
        second.initialize()


def test_openai_embedding_client_is_bounded_below_search_tool_budget(monkeypatch):
    from civil_copilot.stores import qdrant

    captured = {}
    monkeypatch.setattr(qdrant, "OpenAI", lambda **kwargs: captured.update(kwargs) or object())

    qdrant.OpenAIEmbedding("test-key")

    assert captured["timeout"] == 2.0
    assert captured["max_retries"] == 0
