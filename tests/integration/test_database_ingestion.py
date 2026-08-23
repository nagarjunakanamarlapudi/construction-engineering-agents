import os

import pytest

from civil_copilot.config import Settings
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.ingestion.service import IngestionService
from civil_copilot.stores.neo4j import Neo4jGraphStore
from civil_copilot.stores.postgres import PostgresRecordStore
from civil_copilot.stores.qdrant import DeterministicEmbedding, QdrantSearchStore

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1", reason="local Docker services required"
)
def test_all_three_stores_ingest_the_same_corpus_twice_without_duplicates():
    settings = Settings()
    corpus = generate_demo_project(seed=800)
    records = PostgresRecordStore(str(settings.database_url))
    search = QdrantSearchStore(
        str(settings.qdrant_url),
        DeterministicEmbedding(),
        collection_name="civil_copilot_chunks_test",
    )
    graph = Neo4jGraphStore(
        settings.neo4j_uri,
        settings.neo4j_username,
        settings.neo4j_password.get_secret_value(),
    )
    try:
        service = IngestionService(records, search, graph)
        first = service.ingest(corpus.records, corpus.chunks, corpus.relationships)
        second = service.ingest(corpus.records, corpus.chunks, corpus.relationships)

        assert first.records.total == len(corpus.records)
        assert second.records.total == len(corpus.records)
        assert records.count() == len(corpus.records)
        assert search.count() == len(corpus.chunks)
        assert graph.count_nodes(PROJECT_ID := corpus.records[0].project_id) == len(corpus.records)
        assert graph.count_relationships(PROJECT_ID) == len(corpus.relationships)
    finally:
        graph.close()
