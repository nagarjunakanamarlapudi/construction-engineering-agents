import os

import pytest
from fastapi.testclient import TestClient

from civil_copilot.api.main import create_app
from civil_copilot.config import Settings
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.deterministic_model import DeterministicToolCallingModel
from civil_copilot.runtime import build_application_runtime

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1", reason="local Docker services required"
)
def test_local_api_agentic_answer_reads_postgres_qdrant_and_neo4j_without_fallback():
    corpus = generate_demo_project(seed=800)
    application = build_application_runtime(
        mode="local",
        settings=Settings(),
        corpus=corpus,
        model=DeterministicToolCallingModel(),
    )
    try:
        application.ingestion.ingest(corpus.records, corpus.chunks, corpus.relationships)
        second = application.ingestion.ingest(corpus.records, corpus.chunks, corpus.relationships)
        assert second.records.unchanged == len(corpus.records)
        assert second.chunks.unchanged == len(corpus.chunks)
        assert second.relationships.unchanged == len(corpus.relationships)
        live_context = application.tool_context(
            "live-reviewer",
            "BLR-STEEL-DEMO",
            ("project:blr-steel-demo", "public"),
        )
        assert live_context.tool_deadline_runner is not None

        client = TestClient(create_app(application_runtime=application))
        response = client.post(
            "/api/chat",
            json={
                "question": (
                    "Why was activity ACT-STEEL-009 blocked, what changed, "
                    "and what evidence closes the issue?"
                ),
                "route_override": "agentic_rag",
                "user_id": "live-reviewer",
                "project_id": "BLR-STEEL-DEMO",
                "access_scopes": ["project:blr-steel-demo", "public"],
            },
        )

        assert response.status_code == 200
        body = response.json()
        observed_tools = {event["title"] for event in body["trace"] if event["stage"] == "tool"}
        assert observed_tools >= {"get_record", "query_project_graph", "search_documents"}
        assert body["grounded"] is True
        assert body["citations"]
        assert body["evaluation"]["stop_reason"] == "completed"
        assert "tool_deadline_unavailable" not in response.text
        assert application.capabilities.model_dump(mode="json") == {
            "mode": "local",
            "records_backend": "postgresql",
            "search_backend": "qdrant_exact_text_dense",
            "graph_backend": "neo4j",
            "checkpoint_backend": "postgresql",
            "durable_checkpoints": True,
            "server_filtered": True,
            "fallback_allowed": False,
        }
    finally:
        application.close()
