import importlib
from datetime import date

from civil_copilot.agents.react import ReactAgentSuite
from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY
from civil_copilot.agents.tools import ToolRequest
from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.models import Corpus, DocumentChunk, ProjectRecord, Relationship
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.evals.runner import EvaluationRunner
from civil_copilot.memory.service import PreferenceMemory
from civil_copilot.retrieval.query import QueryContext


def test_portable_application_runtime_composes_the_public_restart_safe_contract():
    runtime_module = importlib.import_module("civil_copilot.runtime")
    builder = getattr(runtime_module, "build_application_runtime", None)
    assert callable(builder), "build_application_runtime must be public"
    corpus = generate_demo_project(seed=800)

    application = builder(corpus=corpus)
    try:
        assert application.corpus is corpus
        assert application.capabilities.mode == "portable"
        assert application.capabilities.fallback_allowed is False
        assert application.stores.capabilities == application.capabilities
        assert application.ingestion.records is application.stores.records
        assert application.retrieval is application.tools.retriever
        assert application.tool_registry is DEFAULT_TOOL_REGISTRY
        assert isinstance(application.react_agents, ReactAgentSuite)
        assert application.workflow.tools is application.tools
        assert isinstance(application.memory, PreferenceMemory)
        assert application.workflow.memory is application.memory
        assert application.workflow.tracing is application.tracing
        assert isinstance(application.evaluator, EvaluationRunner)
        assert application.evaluator.run([]).runtime_capabilities["mode"] == "portable"

        context = application.tool_context(
            user_id="reviewer",
            project_id="BLR-STEEL-DEMO",
            access_scopes=("project:blr-steel-demo",),
        )
        result = application.run_react(
            role="orchestrator",
            question=(
                "Why was activity ACT-STEEL-009 blocked, and what evidence closes the issue?"
            ),
            context=context,
        )
        reference = application.trace_reference(result)

        assert result.source_ids
        assert result.tool_names == ["get_record", "query_project_graph", "search_documents"]
        assert reference.provider == "local"
        assert reference.trace_id.startswith("local-run-")
        assert reference.url is None
    finally:
        application.close()


def test_portable_agent_uses_one_standards_tool_and_returns_the_typed_matrix():
    runtime_module = importlib.import_module("civil_copilot.runtime")
    application = runtime_module.build_application_runtime(corpus=load_corpus())
    try:
        context = application.tool_context(
            user_id="reviewer",
            project_id="BLR-STEEL-DEMO",
            access_scopes=("project:blr-steel-demo", "public"),
        )

        result = application.run_react(
            role="document",
            question=(
                "Compare this project's structural-steel practices with the indexed IS 800 "
                "preview. What is evidenced, not evidenced, and needs review?"
            ),
            context=context,
        )

        assert result.stop_reason == "completed"
        assert result.tool_names == ["assess_standard_evidence"]
        assert len(result.observations) == 1
        report = result.observations[0].data["report"]
        assert len(report["rows"]) == 7
        assert {row["status"] for row in report["rows"]} == {
            "Evidenced",
            "Not evidenced",
            "Needs review",
        }
        assert "PUBLIC-BIS-bis-800" in result.source_ids

        response = application.workflow.invoke(
            ChatRequest(
                question=(
                    "Compare this project's structural-steel practices with the indexed IS 800 "
                    "preview. What is evidenced, not evidenced, and needs review?"
                )
            )
        )
        assert response.route == "agentic_rag"
        assert response.grounded is True
        assert response.abstained is False
        assert "Evidenced" in response.answer
        assert "Not evidenced" in response.answer
        assert "Needs review" in response.answer
        assert "not the full Indian Standard" in response.answer
        assert "Missing evidence is not proof" in response.answer
        assert {citation.data_origin for citation in response.citations} == {
            "public_official",
            "synthetic_academic_demo",
        }
    finally:
        application.close()


def test_portable_application_can_start_empty_then_ingest_idempotently():
    runtime_module = importlib.import_module("civil_copilot.runtime")
    corpus = generate_demo_project(seed=800)
    application = runtime_module.build_application_runtime(
        corpus=corpus,
        initialize_data=False,
    )
    try:
        assert application.corpus is corpus
        assert application.stores.records.count() == 0
        assert application.stores.search.count() == 0
        assert application.stores.graph.count_nodes() == 0

        first = application.ingestion.ingest(corpus.records, corpus.chunks, corpus.relationships)
        second = application.ingestion.ingest(corpus.records, corpus.chunks, corpus.relationships)

        assert first.records.created == len(corpus.records)
        assert first.chunks.created == len(corpus.chunks)
        assert first.relationships.created == len(corpus.relationships)
        assert second.records.unchanged == len(corpus.records)
        assert second.chunks.unchanged == len(corpus.chunks)
        assert second.relationships.unchanged == len(corpus.relationships)
    finally:
        application.close()


def test_store_backed_graph_tool_propagates_as_of_date_to_reader():
    runtime_module = importlib.import_module("civil_copilot.runtime")
    records = [
        ProjectRecord(
            record_id=record_id,
            project_id="BLR-STEEL-DEMO",
            record_type="rfi",
            title=record_id,
            content=f"Record {record_id}",
            status="open",
            revision="1",
            effective_date=date(2026, 1, 1),
            data_origin="synthetic_academic_demo",
            source_path=f"test/{record_id}",
            access_scopes=["project:blr-steel-demo"],
        )
        for record_id in ("RFI-PAST", "RFI-FUTURE")
    ]
    chunks = [
        DocumentChunk(
            chunk_id=f"{record.record_id}-chunk",
            record_id=record.record_id,
            project_id=record.project_id,
            text=record.content,
            ordinal=0,
            data_origin=record.data_origin,
            source_path=record.source_path,
            access_scopes=record.access_scopes,
            effective_date=record.effective_date,
        )
        for record in records
    ]
    corpus = Corpus(
        records=records,
        chunks=chunks,
        relationships=[
            Relationship(
                relationship_id="future-edge",
                project_id="BLR-STEEL-DEMO",
                source_id="RFI-PAST",
                target_id="RFI-FUTURE",
                relationship_type="AFFECTS",
                provenance="test",
                method="synthetic_test",
                confidence=1.0,
                valid_from=date(2030, 1, 1),
            )
        ],
    )
    application = runtime_module.build_application_runtime(corpus=corpus)
    try:
        observation = application.tools.call(
            ToolRequest(
                tool_name="find_graph_paths",
                arguments={"start_id": "RFI-PAST", "as_of_date": date(2026, 6, 1)},
                project_id="BLR-STEEL-DEMO",
                access_scopes=["project:blr-steel-demo"],
            )
        )
        assert observation.graph_paths == []
    finally:
        application.close()
        application.close()


def test_portable_application_reports_true_exact_text_and_dense_signal_ranks():
    runtime_module = importlib.import_module("civil_copilot.runtime")
    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        candidates = application.stores.search.search_hybrid(
            query="What did RFI-087 approve?",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            limit=6,
        )
        rfi = next(item for item in candidates if item.chunk.record_id == "RFI-087")
        packet = application.retrieval.retrieve(
            QueryContext(
                question="What did RFI-087 approve?",
                project_id="BLR-STEEL-DEMO",
                access_scopes=["project:blr-steel-demo"],
                top_k=6,
            )
        )

        assert rfi.exact_rank == 1
        assert rfi.text_rank is not None
        assert rfi.dense_rank is not None
        assert packet.retrieval_trace.keyword_candidates > 0
        assert packet.retrieval_trace.vector_candidates > 0
    finally:
        application.close()


def test_every_workflow_route_has_one_real_run_specific_trace_reference():
    runtime_module = importlib.import_module("civil_copilot.runtime")
    application = runtime_module.build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        responses = [
            application.workflow.invoke(
                ChatRequest(
                    question=question,
                    route_override=route,
                    user_id="reviewer",
                )
            )
            for route, question in (
                ("rag", "What did RFI-087 decide?"),
                ("graph_rag", "Trace the downstream path from RFI-087."),
                (
                    "agentic_rag",
                    "Why was ACT-STEEL-009 blocked and what evidence closes it?",
                ),
            )
        ]
        references = [application.trace_reference(response) for response in responses]

        assert all(reference.provider == "local" for reference in references)
        assert all(reference.trace_id.startswith("local-run-") for reference in references)
        assert len({reference.trace_id for reference in references}) == len(references)
        assert all(reference.url is None for reference in references)
    finally:
        application.close()
