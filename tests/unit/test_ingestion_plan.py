from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.ingestion.service import IngestionService
from civil_copilot.stores.base import InMemoryGraphStore, InMemoryRecordStore, InMemorySearchStore


def test_ingestion_is_idempotent_and_preserves_source_identity():
    corpus = generate_demo_project(seed=800)
    record_store = InMemoryRecordStore()
    search_store = InMemorySearchStore()
    graph_store = InMemoryGraphStore()
    service = IngestionService(record_store, search_store, graph_store)

    first = service.ingest(corpus.records, corpus.chunks, corpus.relationships)
    second = service.ingest(corpus.records, corpus.chunks, corpus.relationships)

    assert first.records.created == len(corpus.records)
    assert first.chunks.created == len(corpus.chunks)
    assert first.relationships.created == len(corpus.relationships)
    assert second.records.created == 0
    assert second.records.unchanged == len(corpus.records)
    assert second.chunks.created == 0
    assert second.relationships.created == 0
    assert record_store.records["RFI-087"].source_path.endswith("#RFI-087")
    assert search_store.chunks["RFI-087-chunk-0001"].record_id == "RFI-087"


def test_ingestion_rejects_dangling_relationship_before_any_store_write():
    corpus = generate_demo_project(seed=800)
    broken = corpus.relationships[0].model_copy(update={"target_id": "MISSING-RECORD"})
    record_store = InMemoryRecordStore()
    search_store = InMemorySearchStore()
    graph_store = InMemoryGraphStore()
    service = IngestionService(record_store, search_store, graph_store)

    try:
        service.ingest(corpus.records, corpus.chunks, [broken])
    except ValueError as error:
        assert "MISSING-RECORD" in str(error)
    else:
        raise AssertionError("dangling relationship should have been rejected")

    assert not record_store.records
    assert not search_store.chunks
    assert not graph_store.relationships
