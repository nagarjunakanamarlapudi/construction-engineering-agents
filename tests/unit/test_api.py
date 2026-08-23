from fastapi.testclient import TestClient

from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.api.main import create_app
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever


def _client() -> TestClient:
    corpus = generate_demo_project(seed=800)

    def vector_search(_query: str, limit: int):
        return [(chunk.chunk_id, 0.5) for chunk in corpus.chunks[:limit]]

    workflow = CopilotWorkflow(
        ProjectTools(
            corpus.records,
            HybridRetriever(corpus.chunks, vector_search),
            ProjectGraphService(corpus.records, corpus.relationships),
        )
    )
    return TestClient(create_app(workflow=workflow))


def test_health_and_scenarios_expose_demonstration_contract():
    client = _client()

    health = client.get("/health")
    scenarios = client.get("/api/scenarios")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["workflow"] == "ready"
    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 6


def test_chat_returns_route_visible_trace_evidence_and_grounded_citations():
    client = _client()

    response = client.post(
        "/api/chat",
        json={"question": "What did RFI-087 decide?", "user_id": "reviewer"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag"
    assert body["grounded"] is True
    assert body["citations"]
    assert {event["stage"] for event in body["trace"]} >= {
        "route",
        "plan",
        "tool",
        "evidence",
        "answer",
    }


def test_graph_endpoint_returns_bounded_paths_and_validation_errors_are_clear():
    client = _client()

    graph = client.get("/api/graph/RFI-087?max_depth=2")
    invalid = client.post("/api/chat", json={"question": "x"})

    assert graph.status_code == 200
    assert graph.json()["paths"]
    assert all(len(path["edges"]) <= 2 for path in graph.json()["paths"])
    assert invalid.status_code == 422


def test_record_endpoint_exposes_the_cited_source_record():
    client = _client()

    record = client.get("/api/records/RFI-087")
    missing = client.get("/api/records/UNKNOWN-999")

    assert record.status_code == 200
    assert record.json()["record_id"] == "RFI-087"
    assert record.json()["data_origin"] == "synthetic_academic_demo"
    assert missing.status_code == 404


def test_memory_endpoint_accepts_only_safe_user_preferences():
    client = _client()

    saved = client.post(
        "/api/memory/reviewer",
        json={
            "project_id": "BLR-STEEL-DEMO",
            "preference_type": "answer_style",
            "value": "concise",
        },
    )
    loaded = client.get("/api/memory/reviewer?project_id=BLR-STEEL-DEMO")
    rejected = client.post(
        "/api/memory/reviewer",
        json={
            "project_id": "BLR-STEEL-DEMO",
            "preference_type": "project_status",
            "value": "RFI-087 is closed",
        },
    )

    assert saved.status_code == 200
    assert loaded.json() == {"answer_style": "concise"}
    assert rejected.status_code == 422
