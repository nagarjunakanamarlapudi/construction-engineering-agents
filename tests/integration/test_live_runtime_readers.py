import os
from datetime import date
from pathlib import Path

import pytest

from civil_copilot.config import Settings
from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.ingestion.service import IngestionService
from civil_copilot.runtime import build_runtime
from civil_copilot.stores.qdrant import DeterministicEmbedding, QdrantSearchStore

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1", reason="local Docker services required"
)
def test_live_qdrant_keeps_shipped_legacy_chunk_retrievable_as_of():
    settings = Settings()
    corpus = load_corpus(Path(__file__).parents[2])
    shipped_chunks = [chunk for chunk in corpus.chunks if chunk.record_id == "RFI-087"]
    assert shipped_chunks
    assert all(chunk.effective_date is None for chunk in shipped_chunks)

    store = QdrantSearchStore(
        str(settings.qdrant_url),
        DeterministicEmbedding(),
        collection_name="civil_copilot_chunks_task_1_legacy_as_of_v2",
    )
    try:
        store.upsert_chunks(shipped_chunks)
        candidates = store.search_hybrid(
            query="What did RFI-087 approve?",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            as_of_date=date(2026, 6, 1),
            limit=5,
        )
        assert [candidate.chunk.record_id for candidate in candidates] == ["RFI-087"]
    finally:
        store.client.close()


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1", reason="local Docker services required"
)
def test_local_runtime_reads_filtered_evidence_from_all_three_live_stores():
    settings = Settings()
    corpus = generate_demo_project(seed=800)
    runtime = build_runtime(
        mode="local",
        database_url=str(settings.database_url),
        qdrant_url=str(settings.qdrant_url),
        embedding=DeterministicEmbedding(),
        qdrant_collection_name="civil_copilot_chunks_task_1_v2",
        neo4j_uri=settings.neo4j_uri,
        neo4j_username=settings.neo4j_username,
        neo4j_password=settings.neo4j_password.get_secret_value(),
    )
    try:
        IngestionService(runtime.records, runtime.search, runtime.graph).ingest(
            corpus.records,
            corpus.chunks,
            corpus.relationships,
        )

        records = runtime.records.query_records(
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            record_ids=["RFI-087"],
            as_of_date=date(2026, 6, 1),
        )
        candidates = runtime.search.search_hybrid(
            query="What did RFI-087 approve?",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            metadata_filters={"record_type": "rfi"},
            as_of_date=date(2026, 6, 1),
            limit=5,
        )
        paths = runtime.graph.find_paths(
            "RFI-087",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            max_depth=2,
            direction="outgoing",
            relationship_types={"AFFECTS", "CHANGES_OR_CLARIFIES", "REFERENCES"},
            max_paths=10,
        )
        incoming_paths = runtime.graph.find_paths(
            "RFI-087",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            max_depth=1,
            direction="both",
            relationship_types={"DISCUSSES"},
            max_paths=10,
        )

        assert [record.record_id for record in records] == ["RFI-087"]
        assert candidates[0].chunk.record_id == "RFI-087"
        assert candidates[0].exact_rank == 1
        assert any(path.end_id == "ACT-STEEL-009" for path in paths)
        assert any(
            path.end_id == "MIN-STEEL-07"
            and path.edges[0].source_id == "MIN-STEEL-07"
            and path.edges[0].target_id == "RFI-087"
            for path in incoming_paths
        )
        assert runtime.capabilities.server_filtered is True
    finally:
        runtime.close()
