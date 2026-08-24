import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import APITimeoutError

from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.api.main import create_app
from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.models import Corpus, DocumentChunk, ProjectRecord, Relationship
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.deterministic_model import DeterministicToolCallingModel
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.runtime import build_application_runtime


class RestrictedScheduleModel(DeterministicToolCallingModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if not any(isinstance(message, ToolMessage) for message in messages):
            return self._call(
                "analyze_schedule",
                {
                    "activity_ids": ["ACT-RESTRICTED"],
                    "delay_days": 7,
                    "as_of_date": None,
                },
                1,
            )
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content="Completed permitted schedule analysis."))
            ]
        )


class OpenAIProviderTimeoutModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "openai-timeout-test-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


def _restricted_corpus() -> Corpus:
    base = generate_demo_project(seed=800)
    restricted = ProjectRecord(
        record_id="ACT-RESTRICTED",
        project_id="BLR-STEEL-DEMO",
        record_type="schedule_activity",
        title="Restricted commercial activity",
        content="SECRET-COMMERCIAL-MILESTONE has a seven day exposure.",
        status="blocked",
        revision="1",
        effective_date="2026-02-01",
        data_origin="synthetic_academic_demo",
        source_path="test/restricted.json",
        access_scopes=["role:commercial"],
        metadata={"duration_days": 10, "total_float_days": 0},
    )
    restricted_chunk = DocumentChunk(
        chunk_id="ACT-RESTRICTED-chunk",
        record_id=restricted.record_id,
        project_id=restricted.project_id,
        text=restricted.content,
        ordinal=0,
        data_origin=restricted.data_origin,
        source_path=restricted.source_path,
        access_scopes=restricted.access_scopes,
        effective_date=restricted.effective_date,
    )
    restricted_drawing = ProjectRecord(
        record_id="DRAW-RESTRICTED",
        project_id="BLR-STEEL-DEMO",
        record_type="drawing",
        title="Restricted drawing",
        content="Restricted commercial drawing revision.",
        status="issued",
        revision="9",
        effective_date="2026-02-01",
        data_origin="synthetic_academic_demo",
        source_path="test/restricted-drawing.json",
        access_scopes=["role:commercial"],
        metadata={"document_number": "SEC-001"},
    )
    restricted_drawing_chunk = DocumentChunk(
        chunk_id="DRAW-RESTRICTED-chunk",
        record_id=restricted_drawing.record_id,
        project_id=restricted_drawing.project_id,
        text=restricted_drawing.content,
        ordinal=0,
        data_origin=restricted_drawing.data_origin,
        source_path=restricted_drawing.source_path,
        access_scopes=restricted_drawing.access_scopes,
        effective_date=restricted_drawing.effective_date,
    )
    relationship = Relationship(
        relationship_id="restricted-edge",
        project_id="BLR-STEEL-DEMO",
        source_id="RFI-087",
        target_id=restricted.record_id,
        relationship_type="AFFECTS",
        provenance="test/restricted.json",
        method="synthetic_test",
        confidence=1.0,
        valid_from="2026-02-01",
    )
    return Corpus(
        records=[*base.records, restricted, restricted_drawing],
        chunks=[*base.chunks, restricted_chunk, restricted_drawing_chunk],
        relationships=[*base.relationships, relationship],
    )


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
    assert len(scenarios.json()) == 7
    standards = next(item for item in scenarios.json() if item["scenario_id"] == "S-07")
    assert standards["expected_tools"] == ["assess_standard_evidence"]


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


def test_portable_fastapi_worker_agentic_route_executes_registered_tools():
    runtime = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        with TestClient(create_app(application_runtime=runtime)) as client:
            response = client.post(
                "/api/chat",
                json={
                    "question": (
                        "Why was ACT-STEEL-009 blocked, what changed, "
                        "and what evidence closes the issue?"
                    ),
                    "route_override": "agentic_rag",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["grounded"] is True
        assert body["evaluation"]["stop_reason"] == "completed"
        assert {event["title"] for event in body["trace"] if event["stage"] == "tool"} >= {
            "get_record",
            "query_project_graph",
            "search_documents",
        }
        assert "tool_deadline_unavailable" not in response.text
    finally:
        runtime.close()


def test_chat_returns_safe_non_500_response_when_agent_provider_times_out():
    runtime = build_application_runtime(
        corpus=generate_demo_project(seed=800),
        model=OpenAIProviderTimeoutModel(),
    )
    try:
        with TestClient(
            create_app(application_runtime=runtime),
            raise_server_exceptions=False,
        ) as client:
            response = client.post(
                "/api/chat",
                json={
                    "question": (
                        "Why was ACT-STEEL-009 blocked, what changed in S-204, "
                        "and what activity was affected?"
                    ),
                    "route_override": "agentic_rag",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["route"] == "agentic_rag"
        assert body["grounded"] is False
        assert body["abstained"] is True
        assert body["citations"] == []
        assert body["answer"] == (
            "The investigation reached its time limit without a publishable answer."
        )
        assert body["evaluation"]["stop_reason"] == "time_limit"
        assert body["evaluation"]["review_required"] is False
        assert isinstance(body["evaluation"]["elapsed_ms"], int | float)
        assert isinstance(body["evaluation"]["estimated_cost_usd"], int | float)
        safety = next(
            event
            for event in body["trace"]
            if event["stage"] == "safety" and event["details"].get("stop_reason") == "time_limit"
        )
        assert safety["details"]["error_type"] == "APITimeoutError"
        assert "api.openai.com" not in response.text
    finally:
        runtime.close()


def test_portable_specialist_scenarios_execute_all_six_tools_with_role_allowlists():
    runtime = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        with TestClient(create_app(application_runtime=runtime)) as client:
            responses = [
                client.post(
                    "/api/chat",
                    json={
                        "question": "What changed between S-204 Rev 3 and Rev 5, and why?",
                        "route_override": "agentic_rag",
                    },
                ),
                client.post(
                    "/api/chat",
                    json={
                        "question": (
                            "Why is ACT-STEEL-009 delayed and which milestone is affected?"
                        ),
                        "route_override": "agentic_rag",
                    },
                ),
                client.post(
                    "/api/chat",
                    json={
                        "question": ("Calculate the schedule delay for ACT-STEEL-009 using 2 + 2."),
                        "route_override": "agentic_rag",
                    },
                ),
            ]

        assert all(response.status_code == 200 for response in responses)
        allowed = {
            "document": {"compare_revisions", "get_record", "search_documents"},
            "schedule": {
                "analyze_schedule",
                "calculate",
                "get_record",
                "query_project_graph",
            },
        }
        observed: set[str] = set()
        for response in responses:
            body = response.json()
            specialist = next(
                event["details"]["specialist"]
                for event in body["trace"]
                if event["stage"] == "plan" and event["details"].get("specialist")
            )
            tools = {event["title"] for event in body["trace"] if event["stage"] == "tool"}
            assert tools <= allowed[specialist]
            observed.update(tools)
            assert "tool_deadline_unavailable" not in response.text

        assert observed == {
            "get_record",
            "query_project_graph",
            "search_documents",
            "analyze_schedule",
            "compare_revisions",
            "calculate",
        }
    finally:
        runtime.close()


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


def test_standards_evidence_endpoint_returns_acl_scoped_plain_language_matrix():
    runtime = build_application_runtime(corpus=load_corpus())
    try:
        with TestClient(create_app(application_runtime=runtime)) as client:
            response = client.get("/api/standards/evidence?standard=IS%20800%3A2007")

        assert response.status_code == 200
        report = response.json()
        assert report["project_id"] == "BLR-STEEL-DEMO"
        assert report["standard"] == "IS 800:2007"
        assert len(report["rows"]) == 7
        assert {row["status"] for row in report["rows"]} == {
            "Evidenced",
            "Not evidenced",
            "Needs review",
        }
        assert all(
            row["official_source"]["data_origin"] == "public_official" for row in report["rows"]
        )
        assert "not the full Indian Standard" in report["limitation"]
    finally:
        runtime.close()


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


def test_api_runtime_dependency_exposes_safe_capabilities_and_store_readiness():
    runtime = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        client = TestClient(create_app(application_runtime=runtime))

        health = client.get("/health")
        record = client.get("/api/records/RFI-087")

        assert health.status_code == 200
        assert health.json()["capabilities"] == {
            "mode": "portable",
            "records_backend": "memory",
            "search_backend": "memory_bm25_and_deterministic_dense",
            "graph_backend": "networkx",
            "checkpoint_backend": "memory",
            "durable_checkpoints": False,
            "server_filtered": False,
            "fallback_allowed": False,
        }
        assert health.json()["readiness"] == {
            "records": "ready",
            "search": "ready",
            "graph": "ready",
        }
        assert "password" not in health.text.lower()
        assert record.status_code == 200
        assert record.json()["record_id"] == "RFI-087"
    finally:
        runtime.close()


def test_fastapi_application_honors_explicit_mode_and_never_falls_back(monkeypatch, tmp_path):
    from civil_copilot.api import main

    monkeypatch.setenv("COPILOT_RUNTIME_MODE", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    main.build_application.cache_clear()
    try:
        with pytest.raises(ValueError, match="local mode requires OPENAI_API_KEY"):
            main.build_application()
    finally:
        main.build_application.cache_clear()


def test_api_ignores_self_granted_identity_and_scopes_across_all_read_surfaces():
    runtime = build_application_runtime(
        corpus=_restricted_corpus(),
        model=RestrictedScheduleModel(),
    )
    try:
        with TestClient(create_app(application_runtime=runtime)) as client:
            chat = client.post(
                "/api/chat",
                json={
                    "question": "Why is ACT-RESTRICTED delayed?",
                    "route_override": "agentic_rag",
                    "user_id": "commercial-admin",
                    "project_id": "BLR-STEEL-DEMO",
                    "access_scopes": ["project:blr-steel-demo", "role:commercial"],
                },
            )
            records = client.get("/api/records")
            record = client.get("/api/records/ACT-RESTRICTED")
            graph = client.get("/api/graph/RFI-087?max_depth=2")
            comparison = client.get("/api/compare/SEC-001")
            memory = client.get("/api/memory/commercial-admin")
            other_project = client.post(
                "/api/chat",
                json={
                    "question": "What did RFI-087 decide?",
                    "project_id": "OTHER-PROJECT",
                },
            )

        assert chat.status_code == 200
        assert "ACT-RESTRICTED" not in {
            item["chunk"]["record_id"] for item in chat.json()["evidence"]
        }
        assert "SECRET-COMMERCIAL-MILESTONE" not in chat.text
        assert "ACT-RESTRICTED" not in {item["record_id"] for item in records.json()}
        assert record.status_code == 404
        assert "ACT-RESTRICTED" not in graph.text
        assert comparison.status_code == 404
        assert memory.status_code == 403
        assert other_project.status_code == 403
    finally:
        runtime.close()


def test_api_search_cannot_be_expanded_by_caller_supplied_commercial_scope():
    runtime = build_application_runtime(corpus=_restricted_corpus())
    try:
        with TestClient(create_app(application_runtime=runtime)) as client:
            response = client.post(
                "/api/chat",
                json={
                    "question": "What is SECRET-COMMERCIAL-MILESTONE?",
                    "route_override": "rag",
                    "user_id": "commercial-admin",
                    "access_scopes": ["project:blr-steel-demo", "role:commercial"],
                },
            )

        assert response.status_code == 200
        assert "ACT-RESTRICTED" not in {
            item["chunk"]["record_id"] for item in response.json()["evidence"]
        }
        assert "SECRET-COMMERCIAL-MILESTONE" not in response.json()["answer"]
    finally:
        runtime.close()


def test_health_probes_runtime_and_owned_lifespan_closes_it(monkeypatch):
    from civil_copilot.api import main

    runtime = build_application_runtime(corpus=generate_demo_project(seed=800))
    monkeypatch.setattr(main, "build_application", lambda: runtime)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert runtime._closed is False

    assert runtime._closed is True
    with TestClient(create_app(application_runtime=runtime)) as client:
        health = client.get("/health")
    assert health.status_code == 503
    assert set(health.json()["readiness"].values()) == {"not_ready"}


def test_injected_application_runtime_remains_caller_owned_after_lifespan():
    runtime = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        with TestClient(create_app(application_runtime=runtime)) as client:
            assert client.get("/health").status_code == 200
        assert runtime._closed is False
    finally:
        runtime.close()
