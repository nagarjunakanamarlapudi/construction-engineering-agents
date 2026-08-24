import importlib
import importlib.util
import threading
import time

import pytest
from pydantic import SecretStr

from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY
from civil_copilot.config import Settings
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.ingestion.service import IngestionService


def _runtime_module():
    if importlib.util.find_spec("civil_copilot.runtime") is None:
        return None
    return importlib.import_module("civil_copilot.runtime")


def test_portable_runtime_reports_its_actual_non_server_backends():
    runtime_module = _runtime_module()
    assert runtime_module is not None

    runtime = runtime_module.build_runtime(
        mode="portable",
        corpus=generate_demo_project(seed=800),
    )

    assert runtime.capabilities.model_dump() == {
        "mode": "portable",
        "records_backend": "memory",
        "search_backend": "memory_bm25_and_deterministic_dense",
        "graph_backend": "networkx",
        "checkpoint_backend": "memory",
        "durable_checkpoints": False,
        "server_filtered": False,
        "fallback_allowed": False,
    }
    candidates = runtime.search.search_hybrid(
        query="What did RFI-087 decide?",
        project_id="BLR-STEEL-DEMO",
        access_scopes=["project:blr-steel-demo"],
        metadata_filters={},
        limit=3,
    )
    assert candidates[0].chunk.record_id == "RFI-087"


def test_store_backed_runtime_propagates_connection_failure_instead_of_falling_back(monkeypatch):
    runtime_module = _runtime_module()
    assert runtime_module is not None

    def unavailable(_database_url: str):
        raise ConnectionError("postgres unavailable")

    monkeypatch.setattr(runtime_module, "PostgresRecordStore", unavailable)

    with pytest.raises(ConnectionError, match="postgres unavailable"):
        runtime_module.build_runtime(
            mode="local",
            database_url="postgresql://unused",
            qdrant_url="http://unused",
            embedding=object(),
            neo4j_uri="bolt://unused",
            neo4j_username="neo4j",
            neo4j_password="unused",  # noqa: S106 - inert test value
        )


def test_store_backed_runtime_closes_qdrant_if_neo4j_construction_fails(monkeypatch):
    runtime_module = _runtime_module()
    assert runtime_module is not None

    class TrackingClient:
        closed = False

        def close(self):
            self.closed = True

    client = TrackingClient()
    search = type("SearchAdapter", (), {"client": client})()

    monkeypatch.setattr(runtime_module, "PostgresRecordStore", lambda _url: object())
    monkeypatch.setattr(
        runtime_module,
        "QdrantSearchStore",
        lambda *_args, **_kwargs: search,
    )

    def neo4j_unavailable(*_args):
        raise ConnectionError("neo4j unavailable")

    monkeypatch.setattr(runtime_module, "Neo4jGraphStore", neo4j_unavailable)

    with pytest.raises(ConnectionError, match="neo4j unavailable"):
        runtime_module.build_runtime(
            mode="live",
            database_url="postgresql://unused",
            qdrant_url="http://unused",
            embedding=object(),
            neo4j_uri="bolt://unused",
            neo4j_username="neo4j",
            neo4j_password="unused",  # noqa: S106 - inert test value
        )

    assert client.closed is True


def test_portable_graph_reader_uses_the_same_project_and_acl_contract_as_live_mode():
    runtime_module = _runtime_module()
    assert runtime_module is not None
    runtime = runtime_module.build_runtime(
        mode="portable",
        corpus=generate_demo_project(seed=800),
    )

    visible = runtime.graph.find_paths(
        "RFI-087",
        project_id="BLR-STEEL-DEMO",
        access_scopes=["project:blr-steel-demo"],
        max_depth=2,
        direction="outgoing",
    )
    denied = runtime.graph.find_paths(
        "RFI-087",
        project_id="BLR-STEEL-DEMO",
        access_scopes=["public"],
        max_depth=2,
        direction="outgoing",
    )

    assert any(path.end_id == "ACT-STEEL-009" for path in visible)
    assert denied == []


def test_portable_runtime_accepts_restart_safe_idempotent_ingestion_writes():
    runtime_module = _runtime_module()
    assert runtime_module is not None
    corpus = generate_demo_project(seed=800)
    stores = runtime_module.build_runtime(mode="portable", corpus=corpus)
    ingestion = IngestionService(stores.records, stores.search, stores.graph)

    ingestion.ingest(corpus.records, corpus.chunks, corpus.relationships)
    second = ingestion.ingest(corpus.records, corpus.chunks, corpus.relationships)

    assert second.records.unchanged == len(corpus.records)
    assert second.chunks.unchanged == len(corpus.chunks)
    assert second.relationships.unchanged == len(corpus.relationships)


def test_runtime_close_attempts_every_store_when_graph_close_fails():
    runtime_module = _runtime_module()

    class FailingGraph:
        def close(self):
            raise RuntimeError("graph close failed")

    class SearchClient:
        closed = False

        def close(self):
            self.closed = True

    client = SearchClient()
    runtime = runtime_module.CopilotRuntime(
        records=object(),
        search=type("Search", (), {"client": client})(),
        graph=FailingGraph(),
        capabilities=runtime_module.RuntimeCapabilities(
            mode="local",
            records_backend="postgresql",
            search_backend="qdrant_exact_text_dense",
            graph_backend="neo4j",
            server_filtered=True,
        ),
    )

    with pytest.raises(ExceptionGroup, match="runtime cleanup failed"):
        runtime.close()
    assert client.closed is True


def test_application_close_is_retryable_after_partial_cleanup_failure():
    runtime_module = _runtime_module()
    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))

    class FlakyStores:
        calls = 0

        def close(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary close failure")

    flaky = FlakyStores()
    application.stores = flaky

    with pytest.raises(ExceptionGroup, match="application cleanup failed"):
        application.close()
    assert application._closed is False

    application.close()
    assert application._closed is True
    assert flaky.calls == 2


def test_application_construction_closes_stores_if_later_composition_fails(monkeypatch):
    runtime_module = _runtime_module()

    class TrackingStores:
        closed = False
        records = object()
        search = object()
        graph = object()
        capabilities = runtime_module.RuntimeCapabilities(
            mode="portable",
            records_backend="memory",
            search_backend="memory",
            graph_backend="memory",
            server_filtered=False,
        )

        def close(self):
            self.closed = True

    stores = TrackingStores()
    monkeypatch.setattr(runtime_module, "build_runtime", lambda **_kwargs: stores)
    monkeypatch.setattr(
        runtime_module, "StoreBackedProjectTools", lambda *_args, **_kwargs: object()
    )

    def fail_after_stores(*_args, **_kwargs):
        raise RuntimeError("memory composition failed")

    monkeypatch.setattr(runtime_module, "_application_memory", fail_after_stores)

    with pytest.raises(RuntimeError, match="memory composition failed"):
        runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    assert stores.closed is True


def test_configured_chat_model_uses_timeout_without_exceeding_agent_budget(monkeypatch):
    runtime_module = _runtime_module()
    captured = {}
    expected_model = object()
    monkeypatch.setattr(
        runtime_module,
        "ChatOpenAI",
        lambda **kwargs: captured.update(kwargs) or expected_model,
    )

    model = runtime_module._application_model(
        mode=runtime_module.RuntimeMode.LIVE,
        settings=Settings(
            openai_api_key=SecretStr("test-key"),
            agent_model_request_timeout_seconds=27.0,
            agent_max_seconds=20.0,
        ),
        model=None,
    )

    assert model is expected_model
    assert captured["request_timeout"] == 20.0
    assert captured["reasoning_effort"] == "low"
    assert captured["max_retries"] == 0


def test_local_deterministic_and_live_ingestion_collections_are_explicitly_separate():
    runtime_module = _runtime_module()

    assert runtime_module.application_qdrant_collection("local") == (
        "civil_copilot_chunks_local_deterministic_v2"
    )
    assert runtime_module.application_qdrant_collection("live") == (
        "civil_copilot_chunks_live_openai_v2"
    )
    assert runtime_module.application_qdrant_collection(
        "local"
    ) != runtime_module.application_qdrant_collection("live")


def test_application_deadline_runner_interrupts_main_thread_before_late_mutation():
    runtime_module = _runtime_module()
    from civil_copilot.agents.tool_runtime import ToolDeadlineExceeded

    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    mutations: list[str] = []

    def operation():
        time.sleep(0.15)
        mutations.append("mutated")

    try:
        runner = application.tool_context(
            "reviewer",
            "BLR-STEEL-DEMO",
            ("project:blr-steel-demo",),
        ).tool_deadline_runner
        started = time.monotonic()
        with pytest.raises(ToolDeadlineExceeded):
            runner.run(operation, tool_name="calculate", timeout_seconds=0.02)
        elapsed = time.monotonic() - started
        time.sleep(0.2)

        assert runner.enforces_deadline is True
        assert elapsed < 0.1
        assert mutations == []
    finally:
        application.close()


def test_application_deadline_runner_rejects_unverified_worker_operation_before_mutation():
    from civil_copilot.agents.tool_runtime import ToolDeadlineUnavailable

    runtime_module = _runtime_module()
    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    mutations: list[str] = []
    outcomes: list[object] = []

    def operation():
        time.sleep(0.15)
        mutations.append("mutated")

    def invoke_from_worker():
        try:
            application.tool_context(
                "reviewer",
                "BLR-STEEL-DEMO",
                ("project:blr-steel-demo",),
            ).tool_deadline_runner.run(
                operation,
                tool_name="calculate",
                timeout_seconds=0.02,
            )
        except BaseException as error:
            outcomes.append(error)
        else:
            outcomes.append("completed")

    try:
        thread = threading.Thread(target=invoke_from_worker)
        thread.start()
        thread.join(timeout=1)
        time.sleep(0.2)

        assert not thread.is_alive()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], ToolDeadlineUnavailable)
        assert mutations == []
    finally:
        application.close()


def test_worker_runner_rejects_forged_under_budget_proof_before_mutation():
    from civil_copilot.agents import tool_runtime

    runtime_module = _runtime_module()
    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    mutations: list[str] = []
    outcomes: list[object] = []
    forged_proof = tool_runtime.NativeDeadlineProof(
        tool_name="calculate",
        worst_case_seconds=0.01,
        components=(
            tool_runtime.NativeDeadlineComponent(
                name="forged deterministic bound",
                worst_case_seconds=0.01,
                mechanism="deterministic_bound",
            ),
        ),
    )

    def mutate_late():
        time.sleep(0.15)
        mutations.append("mutated")

    forged_operation = tool_runtime.VerifiedToolOperation(
        operation=mutate_late,
        proof=forged_proof,
    )

    def invoke_from_worker():
        try:
            application.tool_context(
                "reviewer",
                "BLR-STEEL-DEMO",
                ("project:blr-steel-demo",),
            ).tool_deadline_runner.run(
                forged_operation,
                tool_name="calculate",
                timeout_seconds=0.02,
            )
        except BaseException as error:
            outcomes.append(error)
        else:
            outcomes.append("completed")

    try:
        thread = threading.Thread(target=invoke_from_worker)
        thread.start()
        thread.join(timeout=1)
        time.sleep(0.2)

        assert not thread.is_alive()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], tool_runtime.ToolDeadlineUnavailable)
        assert mutations == []
    finally:
        application.close()


def test_worker_runner_rejects_runtime_issued_proof_that_exceeds_requested_budget():
    from civil_copilot.agents import tool_runtime

    runtime_module = _runtime_module()
    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    mutations: list[str] = []
    outcomes: list[object] = []
    operation = application.tools.verified_tool_operation(
        "calculate",
        lambda: mutations.append("mutated"),
    )

    def invoke_from_worker():
        try:
            application.tool_context(
                "reviewer",
                "BLR-STEEL-DEMO",
                ("project:blr-steel-demo",),
            ).tool_deadline_runner.run(
                operation,
                tool_name="calculate",
                timeout_seconds=0.02,
            )
        except BaseException as error:
            outcomes.append(error)

    try:
        thread = threading.Thread(target=invoke_from_worker)
        thread.start()
        thread.join(timeout=1)

        assert isinstance(outcomes[0], tool_runtime.ToolDeadlineUnavailable)
        assert mutations == []
    finally:
        application.close()


def test_application_deadline_proofs_fit_all_registered_tool_budgets():
    runtime_module = _runtime_module()
    proofs = runtime_module.application_deadline_proofs(runtime_module.RuntimeMode.LIVE)

    assert set(proofs) == {
        "search_documents",
        "get_record",
        "query_project_graph",
        "analyze_schedule",
        "compare_revisions",
        "calculate",
        "assess_standard_evidence",
    }
    for tool_name, proof in proofs.items():
        assert proof.tool_name == tool_name
        assert proof.worst_case_seconds < DEFAULT_TOOL_REGISTRY.get(tool_name).time_budget_seconds

    assert [component.name for component in proofs["search_documents"].components] == [
        "openai_embedding",
        "qdrant_exact",
        "qdrant_text",
        "qdrant_dense",
        "openai_reranker",
    ]
    assert DEFAULT_TOOL_REGISTRY.get("search_documents").time_budget_seconds == 16.0


def test_live_deadline_proofs_cover_public_reference_reads_and_retry_attempts():
    runtime_module = _runtime_module()
    proofs = runtime_module.application_deadline_proofs(runtime_module.RuntimeMode.LIVE)

    expected_components = {
        "search_documents": [
            "openai_embedding",
            "qdrant_exact",
            "qdrant_text",
            "qdrant_dense",
            "openai_reranker",
        ],
        "get_record": [
            "attempt_1.postgres_project_record",
            "attempt_1.postgres_public_reference_record",
            "attempt_2.postgres_project_record",
            "attempt_2.postgres_public_reference_record",
        ],
        "query_project_graph": [
            "attempt_1.postgres_project_authorization",
            "attempt_1.postgres_public_reference_authorization",
            "attempt_1.neo4j_connection_acquisition",
            "attempt_1.neo4j_connection",
            "attempt_1.neo4j_path_query",
            "attempt_1.postgres_project_hydration",
            "attempt_1.postgres_public_reference_hydration",
            "attempt_2.postgres_project_authorization",
            "attempt_2.postgres_public_reference_authorization",
            "attempt_2.neo4j_connection_acquisition",
            "attempt_2.neo4j_connection",
            "attempt_2.neo4j_path_query",
            "attempt_2.postgres_project_hydration",
            "attempt_2.postgres_public_reference_hydration",
        ],
        "analyze_schedule": [
            "attempt_1.postgres_project_schedule",
            "attempt_1.postgres_public_reference_schedule",
            "attempt_1.schedule_calculation",
            "attempt_2.postgres_project_schedule",
            "attempt_2.postgres_public_reference_schedule",
            "attempt_2.schedule_calculation",
        ],
        "compare_revisions": [
            "attempt_1.postgres_project_revision",
            "attempt_1.postgres_public_reference_revision",
            "attempt_1.revision_comparison",
            "attempt_2.postgres_project_revision",
            "attempt_2.postgres_public_reference_revision",
            "attempt_2.revision_comparison",
        ],
        "calculate": [
            "attempt_1.bounded_arithmetic",
            "attempt_2.bounded_arithmetic",
        ],
        "assess_standard_evidence": [
            "postgres_project_standard_evidence",
            "postgres_public_standard_preview",
            "standards_evidence_matrix",
        ],
    }
    expected_totals = {
        "search_documents": 9.0,
        "get_record": 8.0,
        "query_project_graph": 25.0,
        "analyze_schedule": 8.5,
        "compare_revisions": 8.5,
        "calculate": 0.5,
        "assess_standard_evidence": 4.25,
    }
    expected_budgets = {
        "search_documents": 16.0,
        "get_record": 9.0,
        "query_project_graph": 26.0,
        "analyze_schedule": 12.0,
        "compare_revisions": 10.0,
        "calculate": 1.0,
        "assess_standard_evidence": 9.0,
    }

    for tool_name, component_names in expected_components.items():
        proof = proofs[tool_name]
        assert [component.name for component in proof.components] == component_names
        assert proof.worst_case_seconds == expected_totals[tool_name]
        assert (
            DEFAULT_TOOL_REGISTRY.get(tool_name).time_budget_seconds == expected_budgets[tool_name]
        )
        assert proof.worst_case_seconds < expected_budgets[tool_name]


def test_live_record_proof_matches_actual_project_and_public_reference_reads():
    from civil_copilot.application_tools import _query_records

    class RecordingReader:
        def __init__(self):
            self.projects: list[str] = []

        def query_records(self, *, project_id: str, **_kwargs):
            self.projects.append(project_id)
            return []

    reader = RecordingReader()
    _query_records(
        reader,
        project_id="BLR-STEEL-DEMO",
        access_scopes=["project:blr-steel-demo", "public"],
    )
    proof = _runtime_module().application_deadline_proofs("live")["get_record"]
    first_attempt_reads = [
        component.name
        for component in proof.components
        if component.name.startswith("attempt_1.postgres_")
    ]

    assert reader.projects == ["BLR-STEEL-DEMO", "PUBLIC-REFERENCE"]
    assert first_attempt_reads == [
        "attempt_1.postgres_project_record",
        "attempt_1.postgres_public_reference_record",
    ]
