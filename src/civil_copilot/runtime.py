"""Explicit portable and store-backed runtime composition without silent fallback."""

from __future__ import annotations

import threading
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Literal, cast
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict

from civil_copilot.agents.react import (
    AgentRole,
    ReactAgentConfig,
    ReactAgentSuite,
    ReactRunResult,
)
from civil_copilot.agents.retry_policy import tool_attempt_count
from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY, ToolRegistry
from civil_copilot.agents.tool_runtime import (
    AgentToolContext,
    NativeDeadlineComponent,
    NativeDeadlineProof,
    SignalToolDeadlineRunner,
    ToolDeadlineRunner,
    ToolDeadlineUnavailable,
    ToolOperation,
    VerifiedToolOperation,
)
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.application_tools import StoreBackedProjectTools, StoreBackedRetriever
from civil_copilot.calculation.service import CalculationService
from civil_copilot.checkpoints import CheckpointResources, create_checkpoint_resources
from civil_copilot.config import Settings
from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.models import Corpus, DocumentChunk, ProjectRecord, Relationship
from civil_copilot.deterministic_model import DeterministicToolCallingModel
from civil_copilot.evals.runner import EvaluationRunner
from civil_copilot.graph.service import GraphPath, ProjectGraphService
from civil_copilot.ingestion.service import IngestionService
from civil_copilot.memory.index import PostgresPreferenceIdIndex
from civil_copilot.memory.service import (
    InMemoryPreferenceBackend,
    Mem0PreferenceBackend,
    PreferenceMemory,
)
from civil_copilot.observability.tracing import TraceReference, TracingBundle, create_tracing
from civil_copilot.retrieval.evidence import HybridCandidate
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.retrieval.query import QueryContext
from civil_copilot.retrieval.rerank import (
    OPENAI_RERANKER_TIMEOUT_SECONDS,
    DeterministicHeuristicReranker,
    OpenAIListwiseReranker,
    Reranker,
    RerankerFailurePolicy,
    extract_identifiers,
)
from civil_copilot.schedule.service import ScheduleImpactService
from civil_copilot.stores.base import (
    GraphReader,
    GraphWriteStats,
    InMemoryGraphStore,
    InMemoryRecordStore,
    InMemorySearchStore,
    RecordReader,
    SearchReader,
    WriteStats,
)
from civil_copilot.stores.neo4j import (
    CONNECTION_ACQUISITION_TIMEOUT_SECONDS as NEO4J_ACQUISITION_TIMEOUT_SECONDS,
)
from civil_copilot.stores.neo4j import (
    CONNECTION_TIMEOUT_SECONDS as NEO4J_CONNECTION_TIMEOUT_SECONDS,
)
from civil_copilot.stores.neo4j import (
    QUERY_TIMEOUT_SECONDS as NEO4J_QUERY_TIMEOUT_SECONDS,
)
from civil_copilot.stores.neo4j import Neo4jGraphStore
from civil_copilot.stores.postgres import (
    STORE_TIMEOUT_SECONDS as POSTGRES_TIMEOUT_SECONDS,
)
from civil_copilot.stores.postgres import PostgresRecordStore
from civil_copilot.stores.qdrant import (
    LIVE_QDRANT_COLLECTION,
    LOCAL_QDRANT_COLLECTION,
    OPENAI_EMBEDDING_TIMEOUT_SECONDS,
    DeterministicEmbedding,
    EmbeddingProvider,
    OpenAIEmbedding,
    QdrantSearchStore,
)
from civil_copilot.stores.qdrant import (
    STORE_TIMEOUT_SECONDS as QDRANT_TIMEOUT_SECONDS,
)

ROOT = Path(__file__).resolve().parents[2]


class RuntimeMode(StrEnum):
    PORTABLE = "portable"
    LOCAL = "local"
    LIVE = "live"


def _deadline_proof(
    tool_name: str,
    components: tuple[NativeDeadlineComponent, ...],
) -> NativeDeadlineProof:
    return NativeDeadlineProof(
        tool_name=tool_name,
        worst_case_seconds=sum(component.worst_case_seconds for component in components),
        components=components,
    )


def _retry_bounded_components(
    tool_name: str,
    components: tuple[NativeDeadlineComponent, ...],
) -> tuple[NativeDeadlineComponent, ...]:
    attempts = tool_attempt_count(tool_name)
    if attempts == 1:
        return components
    return tuple(
        NativeDeadlineComponent(
            name=f"attempt_{attempt}.{component.name}",
            worst_case_seconds=component.worst_case_seconds,
            mechanism=component.mechanism,
        )
        for attempt in range(1, attempts + 1)
        for component in components
    )


def application_deadline_proofs(
    mode: RuntimeMode | str,
) -> dict[str, NativeDeadlineProof]:
    """Return cumulative service-owned bounds for every registered worker-thread tool path."""

    selected_mode = RuntimeMode(mode)
    deterministic = "deterministic_bound"
    native = "native_timeout"
    if selected_mode is RuntimeMode.PORTABLE:
        return {
            "search_documents": _deadline_proof(
                "search_documents",
                (
                    NativeDeadlineComponent("portable_hybrid_search", 2.0, deterministic),
                    NativeDeadlineComponent("portable_reranker", 0.25, deterministic),
                ),
            ),
            "get_record": _deadline_proof(
                "get_record",
                _retry_bounded_components(
                    "get_record",
                    (NativeDeadlineComponent("portable_record_read", 0.25, deterministic),),
                ),
            ),
            "query_project_graph": _deadline_proof(
                "query_project_graph",
                _retry_bounded_components(
                    "query_project_graph",
                    (
                        NativeDeadlineComponent("portable_authorization", 0.25, deterministic),
                        NativeDeadlineComponent("portable_graph_path", 0.5, deterministic),
                        NativeDeadlineComponent("portable_hydration", 0.25, deterministic),
                    ),
                ),
            ),
            "analyze_schedule": _deadline_proof(
                "analyze_schedule",
                _retry_bounded_components(
                    "analyze_schedule",
                    (
                        NativeDeadlineComponent("portable_schedule_read", 0.25, deterministic),
                        NativeDeadlineComponent("schedule_calculation", 0.25, deterministic),
                    ),
                ),
            ),
            "compare_revisions": _deadline_proof(
                "compare_revisions",
                _retry_bounded_components(
                    "compare_revisions",
                    (
                        NativeDeadlineComponent("portable_revision_read", 0.25, deterministic),
                        NativeDeadlineComponent("revision_comparison", 0.25, deterministic),
                    ),
                ),
            ),
            "calculate": _deadline_proof(
                "calculate",
                _retry_bounded_components(
                    "calculate",
                    (NativeDeadlineComponent("bounded_arithmetic", 0.25, deterministic),),
                ),
            ),
            "assess_standard_evidence": _deadline_proof(
                "assess_standard_evidence",
                (
                    NativeDeadlineComponent(
                        "portable_project_and_public_record_read", 0.5, deterministic
                    ),
                    NativeDeadlineComponent("standards_evidence_matrix", 0.25, deterministic),
                ),
            ),
        }

    postgres_read_seconds = POSTGRES_TIMEOUT_SECONDS * 2
    embedding_component = (
        NativeDeadlineComponent(
            "openai_embedding",
            OPENAI_EMBEDDING_TIMEOUT_SECONDS,
            native,
        )
        if selected_mode is RuntimeMode.LIVE
        else NativeDeadlineComponent("deterministic_embedding", 0.5, deterministic)
    )
    return {
        "search_documents": _deadline_proof(
            "search_documents",
            (
                embedding_component,
                NativeDeadlineComponent("qdrant_exact", QDRANT_TIMEOUT_SECONDS, native),
                NativeDeadlineComponent("qdrant_text", QDRANT_TIMEOUT_SECONDS, native),
                NativeDeadlineComponent("qdrant_dense", QDRANT_TIMEOUT_SECONDS, native),
                NativeDeadlineComponent(
                    "openai_reranker",
                    OPENAI_RERANKER_TIMEOUT_SECONDS,
                    native,
                ),
            ),
        ),
        "get_record": _deadline_proof(
            "get_record",
            _retry_bounded_components(
                "get_record",
                (
                    NativeDeadlineComponent(
                        "postgres_project_record", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent(
                        "postgres_public_reference_record", postgres_read_seconds, native
                    ),
                ),
            ),
        ),
        "query_project_graph": _deadline_proof(
            "query_project_graph",
            _retry_bounded_components(
                "query_project_graph",
                (
                    NativeDeadlineComponent(
                        "postgres_project_authorization", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent(
                        "postgres_public_reference_authorization",
                        postgres_read_seconds,
                        native,
                    ),
                    NativeDeadlineComponent(
                        "neo4j_connection_acquisition",
                        NEO4J_ACQUISITION_TIMEOUT_SECONDS,
                        native,
                    ),
                    NativeDeadlineComponent(
                        "neo4j_connection",
                        NEO4J_CONNECTION_TIMEOUT_SECONDS,
                        native,
                    ),
                    NativeDeadlineComponent(
                        "neo4j_path_query", NEO4J_QUERY_TIMEOUT_SECONDS, native
                    ),
                    NativeDeadlineComponent(
                        "postgres_project_hydration", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent(
                        "postgres_public_reference_hydration",
                        postgres_read_seconds,
                        native,
                    ),
                ),
            ),
        ),
        "analyze_schedule": _deadline_proof(
            "analyze_schedule",
            _retry_bounded_components(
                "analyze_schedule",
                (
                    NativeDeadlineComponent(
                        "postgres_project_schedule", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent(
                        "postgres_public_reference_schedule", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent("schedule_calculation", 0.25, deterministic),
                ),
            ),
        ),
        "compare_revisions": _deadline_proof(
            "compare_revisions",
            _retry_bounded_components(
                "compare_revisions",
                (
                    NativeDeadlineComponent(
                        "postgres_project_revision", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent(
                        "postgres_public_reference_revision", postgres_read_seconds, native
                    ),
                    NativeDeadlineComponent("revision_comparison", 0.25, deterministic),
                ),
            ),
        ),
        "calculate": _deadline_proof(
            "calculate",
            _retry_bounded_components(
                "calculate",
                (NativeDeadlineComponent("bounded_arithmetic", 0.25, deterministic),),
            ),
        ),
        "assess_standard_evidence": _deadline_proof(
            "assess_standard_evidence",
            (
                NativeDeadlineComponent(
                    "postgres_project_standard_evidence", postgres_read_seconds, native
                ),
                NativeDeadlineComponent(
                    "postgres_public_standard_preview", postgres_read_seconds, native
                ),
                NativeDeadlineComponent("standards_evidence_matrix", 0.25, deterministic),
            ),
        ),
    }


class RuntimeCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: RuntimeMode
    records_backend: str
    search_backend: str
    graph_backend: str
    checkpoint_backend: str = "memory"
    durable_checkpoints: bool = False
    server_filtered: bool
    fallback_allowed: bool = False


class PortableSearchReader:
    """Portable teaching reader using in-process BM25 and supplied deterministic vectors."""

    def __init__(self, corpus: Corpus, embedding: EmbeddingProvider) -> None:
        self.embedding = embedding
        self.store = InMemorySearchStore()
        self.store.upsert_chunks(corpus.chunks)
        self._rebuild()

    def _rebuild(self) -> None:
        chunks = sorted(self.store.chunks.values(), key=lambda chunk: chunk.chunk_id)
        vectors = {chunk.chunk_id: self.embedding.embed_query(chunk.text) for chunk in chunks}

        def vector_search(query: str, limit: int) -> list[tuple[str, float]]:
            query_vector = self.embedding.embed_query(query)
            scores = [
                (
                    chunk_id,
                    sum(left * right for left, right in zip(query_vector, vector, strict=True)),
                )
                for chunk_id, vector in vectors.items()
            ]
            return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]

        self.retriever = HybridRetriever(chunks, vector_search)

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> WriteStats:
        stats = self.store.upsert_chunks(chunks)
        if stats.created or stats.updated:
            self._rebuild()
        return stats

    def count(self) -> int:
        return self.store.count()

    def search_hybrid(
        self,
        *,
        query: str,
        project_id: str,
        access_scopes: list[str],
        metadata_filters: dict[str, object] | None = None,
        as_of_date: date | None = None,
        limit: int = 20,
    ) -> list[HybridCandidate]:
        context = QueryContext(
            question=query,
            project_id=project_id,
            access_scopes=access_scopes,
            filters=metadata_filters or {},
            as_of_date=as_of_date,
            top_k=min(max(limit, 1), 20),
        )
        candidates, _keyword_count, _vector_count, _eligible_count = (
            self.retriever.search_candidates(context)
        )
        eligible = [
            chunk for chunk in self.retriever.chunks if self.retriever._eligible(chunk, context)
        ]
        eligible_ids = {chunk.chunk_id for chunk in eligible}
        identifiers = set(extract_identifiers(query))
        exact_ids = [
            chunk.chunk_id
            for chunk in sorted(eligible, key=lambda item: item.chunk_id)
            if chunk.record_id.upper() in identifiers
        ]
        text_ids = self.retriever._keyword_ranking(query, eligible)
        # The portable corpus is intentionally small; inspect the full bounded
        # branch window so returned text/exact candidates retain their real
        # deterministic-dense rank instead of presenting that signal as absent.
        branch_limit = 100
        dense_ids = [
            chunk_id
            for chunk_id, _score in self.retriever.vector_search(query, branch_limit)
            if chunk_id in eligible_ids
        ]
        exact_ranks = {chunk_id: rank for rank, chunk_id in enumerate(exact_ids, start=1)}
        text_ranks = {chunk_id: rank for rank, chunk_id in enumerate(text_ids, start=1)}
        dense_ranks = {chunk_id: rank for rank, chunk_id in enumerate(dense_ids, start=1)}
        return [
            HybridCandidate(
                chunk=item.chunk,
                fused_score=item.fused_score,
                exact_rank=exact_ranks.get(item.chunk.chunk_id),
                text_rank=text_ranks.get(item.chunk.chunk_id),
                dense_rank=dense_ranks.get(item.chunk.chunk_id),
            )
            for item in candidates
        ]


class PortableGraphReader:
    """Portable graph adapter with the same authorization contract as Neo4j."""

    def __init__(self, corpus: Corpus) -> None:
        self.store = InMemoryGraphStore()
        self.store.upsert_graph(corpus.records, corpus.relationships)
        self._rebuild()

    def _rebuild(self) -> None:
        self.records = self.store.nodes
        self.service = ProjectGraphService(
            list(self.store.nodes.values()), list(self.store.relationships.values())
        )

    def upsert_graph(
        self, records: list[ProjectRecord], relationships: list[Relationship]
    ) -> GraphWriteStats:
        stats = self.store.upsert_graph(records, relationships)
        if (
            stats.nodes.created
            or stats.nodes.updated
            or stats.relationships.created
            or stats.relationships.updated
        ):
            self._rebuild()
        return stats

    def count_nodes(self, project_id: str | None = None) -> int:
        return self.store.count_nodes(project_id)

    def count_relationships(self, project_id: str | None = None) -> int:
        return self.store.count_relationships(project_id)

    def find_paths(
        self,
        start_id: str,
        *,
        project_id: str,
        access_scopes: list[str],
        max_depth: int = 3,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        as_of_date: date | None = None,
        max_paths: int = 30,
    ) -> list[GraphPath]:
        permitted_scopes = set(access_scopes)

        def permitted(record_id: str) -> bool:
            record = self.records[record_id]
            return (
                record.project_id == project_id
                and bool(permitted_scopes & set(record.access_scopes))
                and (as_of_date is None or record.effective_date <= as_of_date)
            )

        if start_id not in self.records or not permitted(start_id):
            return []
        paths = self.service.find_paths(
            start_id,
            max_depth=max_depth,
            direction=direction,
            relationship_types=relationship_types,
            max_paths=max_paths,
        )
        return [
            path
            for path in paths
            if all(permitted(node.record_id) for node in path.nodes)
            and (
                as_of_date is None
                or all(
                    edge.valid_from is None or edge.valid_from <= as_of_date for edge in path.edges
                )
            )
        ]


@dataclass
class CopilotRuntime:
    records: RecordReader
    search: SearchReader
    graph: GraphReader
    capabilities: RuntimeCapabilities

    def close(self) -> None:
        errors: list[Exception] = []
        close_graph = getattr(self.graph, "close", None)
        if close_graph:
            try:
                close_graph()
            except Exception as error:  # noqa: BLE001 - cleanup must continue
                errors.append(error)
        try:
            _close_search(self.search)
        except Exception as error:  # noqa: BLE001 - cleanup must continue
            errors.append(error)
        if errors:
            raise ExceptionGroup("runtime cleanup failed", errors)


def _close_search(search: object) -> None:
    search_client = getattr(search, "client", None)
    close_search = getattr(search_client, "close", None)
    if close_search:
        close_search()


def build_runtime(
    *,
    mode: RuntimeMode | str,
    corpus: Corpus | None = None,
    database_url: str | None = None,
    qdrant_url: str | None = None,
    embedding: EmbeddingProvider | None = None,
    qdrant_api_key: str | None = None,
    qdrant_collection_name: str = "civil_copilot_chunks_v2",
    neo4j_uri: str | None = None,
    neo4j_username: str | None = None,
    neo4j_password: str | None = None,
) -> CopilotRuntime:
    """Build exactly the requested runtime or raise; never substitute another mode."""

    selected_mode = RuntimeMode(mode)
    if selected_mode is RuntimeMode.PORTABLE:
        if corpus is None:
            raise ValueError("portable mode requires a corpus")
        from civil_copilot.stores.qdrant import DeterministicEmbedding

        records = InMemoryRecordStore()
        records.upsert_records(corpus.records)
        return CopilotRuntime(
            records=records,
            search=PortableSearchReader(corpus, DeterministicEmbedding()),
            graph=PortableGraphReader(corpus),
            capabilities=RuntimeCapabilities(
                mode=selected_mode,
                records_backend="memory",
                search_backend="memory_bm25_and_deterministic_dense",
                graph_backend="networkx",
                checkpoint_backend="memory",
                durable_checkpoints=False,
                server_filtered=False,
            ),
        )

    missing = [
        name
        for name, value in {
            "database_url": database_url,
            "qdrant_url": qdrant_url,
            "embedding": embedding,
            "neo4j_uri": neo4j_uri,
            "neo4j_username": neo4j_username,
            "neo4j_password": neo4j_password,
        }.items()
        if value is None
    ]
    if missing:
        raise ValueError(f"{selected_mode.value} mode is missing: {', '.join(missing)}")

    records = PostgresRecordStore(database_url)
    search = QdrantSearchStore(
        qdrant_url,
        embedding,
        api_key=qdrant_api_key,
        collection_name=qdrant_collection_name,
    )
    try:
        graph = Neo4jGraphStore(neo4j_uri, neo4j_username, neo4j_password)
    except Exception:
        # Cleanup must not hide the construction failure that made the
        # requested explicit runtime unavailable.
        with suppress(Exception):
            _close_search(search)
        raise
    return CopilotRuntime(
        records=records,
        search=search,
        graph=graph,
        capabilities=RuntimeCapabilities(
            mode=selected_mode,
            records_backend="postgresql",
            search_backend="qdrant_exact_text_dense",
            graph_backend="neo4j",
            checkpoint_backend="postgresql",
            durable_checkpoints=True,
            server_filtered=True,
        ),
    )


@dataclass
class ApplicationRuntime:
    """One explicit composition root shared by API, notebooks, tools, and evaluations."""

    capabilities: RuntimeCapabilities
    corpus: Corpus
    stores: CopilotRuntime
    ingestion: IngestionService
    retrieval: StoreBackedRetriever
    tools: StoreBackedProjectTools
    tool_registry: ToolRegistry
    react_agents: ReactAgentSuite
    workflow: CopilotWorkflow
    memory: PreferenceMemory
    tracing: TracingBundle
    checkpoints: CheckpointResources
    evaluator: EvaluationRunner
    _context_factory: RuntimeToolContextFactory
    _closed: bool = field(default=False, init=False, repr=False)

    def tool_context(
        self,
        user_id: str,
        project_id: str,
        access_scopes: tuple[str, ...] | list[str],
        *,
        conversation_id: str | None = None,
    ) -> AgentToolContext:
        return self._context_factory(
            user_id,
            project_id,
            access_scopes,
            conversation_id=conversation_id,
        )

    def run_react(
        self,
        *,
        role: AgentRole,
        question: str,
        context: AgentToolContext,
        max_steps: int | None = None,
    ) -> TracedReactRun:
        with self.tracing.run(
            f"react:{role}",
            {"question": question, "project_id": context.project_id},
        ) as trace_run:
            result = self.react_agents.run(
                role=role,
                question=question,
                context=context,
                callbacks=trace_run.callbacks,
                max_steps=max_steps,
            )
        return TracedReactRun(result=result, trace_reference=trace_run.reference)

    def trace_reference(self, result: object) -> TraceReference:
        existing = getattr(result, "trace_reference", None)
        if isinstance(existing, TraceReference):
            return existing
        return self.tracing.reference()

    def readiness(self) -> dict[str, str]:
        if self._closed:
            return {name: "not_ready" for name in ("records", "search", "graph")}
        probes = {
            "records": lambda: self.stores.records.count(),
            "search": lambda: self.stores.search.count(),
            "graph": lambda: self.stores.graph.count_nodes(),
        }
        readiness: dict[str, str] = {}
        for name, probe in probes.items():
            try:
                probe()
            except Exception:  # noqa: BLE001 - public readiness never exposes backend detail
                readiness[name] = "not_ready"
            else:
                readiness[name] = "ready"
        return readiness

    def close(self) -> None:
        if self._closed:
            return
        errors: list[Exception] = []
        try:
            self.tracing.flush()
        except Exception as error:  # noqa: BLE001 - cleanup must continue
            errors.append(error)
        try:
            self.checkpoints.close()
        except Exception as error:  # noqa: BLE001 - cleanup must continue
            errors.append(error)
        try:
            self.stores.close()
        except Exception as error:  # noqa: BLE001 - cleanup must continue
            errors.append(error)
        if errors:
            raise ExceptionGroup("application cleanup failed", errors)
        self._closed = True


@dataclass(frozen=True)
class TracedReactRun:
    result: ReactRunResult
    trace_reference: TraceReference

    def __getattr__(self, name: str):
        return getattr(self.result, name)


@dataclass(frozen=True)
class RuntimeToolContextFactory:
    records: RecordReader
    tools: StoreBackedProjectTools

    def __call__(
        self,
        user_id: str,
        project_id: str,
        access_scopes: tuple[str, ...] | list[str],
        *,
        conversation_id: str | None = None,
    ) -> AgentToolContext:
        scopes = tuple(access_scopes)
        schedule_records = self.records.query_records(
            project_id=project_id,
            access_scopes=list(scopes),
            record_types=["schedule_activity"],
            limit=500,
        )
        deadline_runner: ToolDeadlineRunner = StoreBackedToolDeadlineRunner(self.tools)
        return AgentToolContext(
            user_id=user_id,
            project_id=project_id,
            access_scopes=scopes,
            project_tools=self.tools,
            schedule_service=ScheduleImpactService(schedule_records),
            calculation_service=CalculationService(),
            request_id=f"{user_id}-{uuid4()}",
            conversation_id=conversation_id or f"conversation-{uuid4().hex}",
            tool_deadline_runner=deadline_runner,
        )


@dataclass(frozen=True)
class StoreBackedToolDeadlineRunner:
    """Enforce main-thread deadlines and trust only bounded application adapters in workers."""

    project_tools: StoreBackedProjectTools
    enforces_deadline: ClassVar[Literal[True]] = True
    requires_native_deadline_proof: ClassVar[Literal[True]] = True

    def __post_init__(self) -> None:
        if not isinstance(self.project_tools, StoreBackedProjectTools):
            raise TypeError("worker deadline runner requires StoreBackedProjectTools")

    def run(
        self,
        operation: ToolOperation,
        *,
        tool_name: str,
        timeout_seconds: float,
    ) -> Any:
        if timeout_seconds <= 0:
            raise ToolDeadlineUnavailable(f"{tool_name} has no positive deadline")
        if threading.current_thread() is threading.main_thread():
            return SignalToolDeadlineRunner().run(
                operation,
                tool_name=tool_name,
                timeout_seconds=timeout_seconds,
            )
        if not self.project_tools.issued_tool_operation(operation, tool_name):
            raise ToolDeadlineUnavailable(
                f"worker execution for {tool_name} requires a native deadline proof"
            )
        operation = cast(VerifiedToolOperation, operation)
        proof = operation.proof
        if proof.tool_name != tool_name or proof.worst_case_seconds >= timeout_seconds:
            raise ToolDeadlineUnavailable(
                f"native deadline proof for {tool_name} does not fit its registered budget"
            )
        return operation()


def _application_memory(settings: Settings, mode: RuntimeMode) -> PreferenceMemory:
    if mode is RuntimeMode.PORTABLE or settings.mem0_api_key is None:
        return PreferenceMemory(InMemoryPreferenceBackend())
    return PreferenceMemory(
        Mem0PreferenceBackend(
            settings.mem0_api_key.get_secret_value(),
            preference_index=PostgresPreferenceIdIndex(str(settings.database_url)),
        )
    )


def _application_model(
    *,
    mode: RuntimeMode,
    settings: Settings,
    model: BaseChatModel | None,
) -> BaseChatModel:
    if model is not None:
        return model
    if mode is RuntimeMode.PORTABLE:
        return DeterministicToolCallingModel()
    if settings.openai_api_key is None:
        raise ValueError(f"{mode.value} mode requires OPENAI_API_KEY when model is not supplied")
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        request_timeout=min(
            settings.agent_model_request_timeout_seconds,
            settings.agent_max_seconds,
        ),
        reasoning_effort=settings.agent_reasoning_effort,
        max_retries=0,
    )


def build_application_reranker(
    *,
    mode: RuntimeMode | str,
    settings: Settings,
) -> Reranker:
    """Select the explicit second-stage reranker for one runtime mode."""

    selected_mode = RuntimeMode(mode)
    if selected_mode is RuntimeMode.PORTABLE:
        return DeterministicHeuristicReranker()
    if settings.openai_api_key is None:
        raise ValueError(f"{selected_mode.value} mode requires OPENAI_API_KEY for reranking")
    reranker_model = ChatOpenAI(
        model=settings.openai_reranker_model,
        api_key=settings.openai_api_key,
        request_timeout=settings.reranker_timeout_seconds,
        max_retries=0,
    )
    return OpenAIListwiseReranker(
        chat_model=reranker_model,
        model_name=settings.openai_reranker_model,
        model_version=settings.openai_reranker_version,
        failure_policy=RerankerFailurePolicy(settings.reranker_failure_policy),
        max_candidates=settings.reranker_max_candidates,
        max_text_chars=settings.reranker_max_text_chars,
    )


def application_qdrant_collection(mode: RuntimeMode | str) -> str:
    """Return the explicit vector schema boundary for one store-backed mode."""

    selected_mode = RuntimeMode(mode)
    if selected_mode is RuntimeMode.PORTABLE:
        raise ValueError("portable mode has no Qdrant collection")
    return LIVE_QDRANT_COLLECTION if selected_mode is RuntimeMode.LIVE else LOCAL_QDRANT_COLLECTION


def build_application_runtime(
    *,
    mode: RuntimeMode | str = RuntimeMode.PORTABLE,
    settings: Settings | None = None,
    corpus: Corpus | None = None,
    model: BaseChatModel | None = None,
    initialize_data: bool = True,
) -> ApplicationRuntime:
    """Build the requested application runtime exactly; never substitute another mode."""

    selected_mode = RuntimeMode(mode)
    selected_settings = settings or Settings()
    selected_corpus = corpus or load_corpus(ROOT)
    selected_model = _application_model(
        mode=selected_mode,
        settings=selected_settings,
        model=model,
    )
    reranker = build_application_reranker(mode=selected_mode, settings=selected_settings)
    if selected_mode is RuntimeMode.PORTABLE:
        stores = build_runtime(
            mode=selected_mode,
            corpus=selected_corpus if initialize_data else Corpus(),
        )
    else:
        if selected_mode is RuntimeMode.LIVE:
            if selected_settings.openai_api_key is None:
                raise ValueError("live mode requires OPENAI_API_KEY for embeddings")
            embedding: EmbeddingProvider = OpenAIEmbedding(
                selected_settings.openai_api_key.get_secret_value(),
                selected_settings.openai_embedding_model,
            )
        else:
            embedding = DeterministicEmbedding()
        stores = build_runtime(
            mode=selected_mode,
            database_url=str(selected_settings.database_url),
            qdrant_url=str(selected_settings.qdrant_url),
            embedding=embedding,
            qdrant_api_key=(
                selected_settings.qdrant_api_key.get_secret_value()
                if selected_settings.qdrant_api_key
                else None
            ),
            qdrant_collection_name=(application_qdrant_collection(selected_mode)),
            neo4j_uri=selected_settings.neo4j_uri,
            neo4j_username=selected_settings.neo4j_username,
            neo4j_password=selected_settings.neo4j_password.get_secret_value(),
        )

    checkpoints: CheckpointResources | None = None
    try:
        checkpoints = create_checkpoint_resources(
            mode=selected_mode.value,
            database_url=(
                str(selected_settings.database_url)
                if selected_mode is not RuntimeMode.PORTABLE
                else None
            ),
        )
        project_records = [
            record for record in selected_corpus.records if record.project_id != "PUBLIC-REFERENCE"
        ]
        default_project_id = project_records[0].project_id if project_records else "BLR-STEEL-DEMO"
        default_access_scopes = tuple(
            dict.fromkeys(
                scope
                for record in selected_corpus.records
                if record.project_id in {default_project_id, "PUBLIC-REFERENCE"}
                for scope in record.access_scopes
                if scope == "public" or scope.startswith("project:")
            )
        )
        tools = StoreBackedProjectTools(
            stores.records,
            stores.search,
            stores.graph,
            default_project_id=default_project_id,
            default_access_scopes=default_access_scopes,
            deadline_proofs=application_deadline_proofs(selected_mode),
            reranker=reranker,
        )
        context_factory = RuntimeToolContextFactory(stores.records, tools)
        memory = _application_memory(selected_settings, selected_mode)
        tracing = (
            create_tracing(selected_settings)
            if selected_mode is not RuntimeMode.PORTABLE
            else TracingBundle(enabled=False)
        )
        registry = DEFAULT_TOOL_REGISTRY
        react_agents = ReactAgentSuite(
            selected_model,
            registry=registry,
            checkpointer=checkpoints.saver,
            config=ReactAgentConfig(
                max_model_calls=selected_settings.agent_max_model_calls,
                max_tool_calls=selected_settings.agent_max_tool_calls,
                max_seconds=selected_settings.agent_max_seconds,
                max_cost_usd=selected_settings.agent_max_cost_usd,
                input_cost_per_1k_tokens=(selected_settings.agent_input_cost_per_1k_tokens),
                output_cost_per_1k_tokens=(selected_settings.agent_output_cost_per_1k_tokens),
            ),
        )
        workflow = CopilotWorkflow(
            tools,
            tracing=tracing,
            memory=memory,
            react_agents=react_agents,
            tool_context_factory=context_factory,
        )
        application = ApplicationRuntime(
            capabilities=stores.capabilities,
            corpus=selected_corpus,
            stores=stores,
            ingestion=IngestionService(stores.records, stores.search, stores.graph),
            retrieval=tools.retriever,
            tools=tools,
            tool_registry=registry,
            react_agents=react_agents,
            workflow=workflow,
            memory=memory,
            tracing=tracing,
            checkpoints=checkpoints,
            evaluator=EvaluationRunner(workflow, runtime_capabilities=stores.capabilities),
            _context_factory=context_factory,
        )
        workflow.tool_context_factory = application.tool_context
        return application
    except Exception:
        if checkpoints is not None:
            with suppress(Exception):
                checkpoints.close()
        with suppress(Exception):
            stores.close()
        raise
