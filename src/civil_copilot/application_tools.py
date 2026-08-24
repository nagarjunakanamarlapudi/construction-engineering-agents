"""Store-backed retrieval and project-tool adapters for application composition."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import date
from typing import Any

from civil_copilot.agents.tool_runtime import (
    NativeDeadlineProof,
    ToolDeadlineUnavailable,
    VerifiedToolOperation,
)
from civil_copilot.agents.tools import (
    ALLOWED_TOOLS,
    ProjectTools,
    ToolObservation,
    ToolRequest,
)
from civil_copilot.data.models import ProjectRecord
from civil_copilot.graph.service import GraphPath
from civil_copilot.retrieval.evidence import EvidencePacket, HybridCandidate, RetrievalTrace
from civil_copilot.retrieval.query import QueryContext
from civil_copilot.retrieval.rerank import (
    DeterministicHeuristicReranker,
    Reranker,
    extract_identifiers,
)
from civil_copilot.stores.base import GraphReader, RecordReader, SearchReader


class StoreBackedRetriever:
    """Translate the store search contract into the workflow evidence contract."""

    def __init__(self, search: SearchReader, *, reranker: Reranker | None = None) -> None:
        self.search = search
        self.reranker = reranker or DeterministicHeuristicReranker()

    @staticmethod
    def _eligible(candidate: HybridCandidate, context: QueryContext) -> bool:
        chunk = candidate.chunk
        return (
            chunk.project_id in {context.project_id, "PUBLIC-REFERENCE"}
            and bool(set(chunk.access_scopes) & set(context.access_scopes))
            and all(chunk.metadata.get(key) == value for key, value in context.filters.items())
            and (
                context.as_of_date is None
                or chunk.effective_date is None
                or chunk.effective_date <= context.as_of_date
            )
        )

    def retrieve(self, context: QueryContext) -> EvidencePacket:
        candidates = self.search.search_hybrid(
            query=context.question,
            project_id=context.project_id,
            access_scopes=context.access_scopes,
            metadata_filters=context.filters,
            as_of_date=context.as_of_date,
            limit=min(max(context.top_k * 4, 20), 100),
        )
        candidates = [candidate for candidate in candidates if self._eligible(candidate, context)]
        candidates.sort(key=lambda item: (-item.fused_score, item.chunk.chunk_id))
        outcome = self.reranker.rerank(context.question, candidates)
        evidence = outcome.evidence
        considered_ids = set(outcome.trace.input_candidate_ids)
        returned = [item for item in evidence if item.rerank_score >= context.minimum_rerank_score][
            : context.top_k
        ]
        return EvidencePacket(
            question=context.question,
            evidence=returned,
            retrieval_trace=RetrievalTrace(
                keyword_candidates=sum(item.text_rank is not None for item in candidates),
                vector_candidates=sum(item.dense_rank is not None for item in candidates),
                fused_candidates=len(candidates),
                filtered_candidates=len(candidates),
                returned_evidence=len(returned),
                exact_identifiers=extract_identifiers(context.question),
                hybrid_ranking=list(
                    dict.fromkeys(
                        item.chunk.record_id
                        for item in candidates
                        if item.chunk.chunk_id in considered_ids
                    )
                ),
                reranked_ranking=list(dict.fromkeys(item.chunk.record_id for item in evidence)),
                reranker=outcome.trace,
            ),
        )


class OnlineRecordView(Mapping[str, ProjectRecord]):
    """Mapping-compatible view that resolves every operation through the record reader."""

    def __init__(
        self,
        records: RecordReader,
        *,
        project_id: str,
        access_scopes: tuple[str, ...],
    ) -> None:
        self.reader = records
        self.project_id = project_id
        self.access_scopes = access_scopes

    def _query(self, record_ids: list[str] | None = None) -> list[ProjectRecord]:
        return _query_records(
            self.reader,
            project_id=self.project_id,
            access_scopes=list(self.access_scopes),
            record_ids=record_ids,
            limit=500,
        )

    def __getitem__(self, key: str) -> ProjectRecord:
        rows = self._query([key])
        if not rows:
            raise KeyError(key)
        return rows[0]

    def __iter__(self) -> Iterator[str]:
        return iter(record.record_id for record in self._query())

    def __len__(self) -> int:
        return len(self._query())

    def values(self) -> list[ProjectRecord]:
        return self._query()


class DefaultScopedGraphView:
    """Legacy workflow/API graph surface backed by the selected online graph reader."""

    def __init__(
        self,
        graph: GraphReader,
        *,
        project_id: str,
        access_scopes: tuple[str, ...],
    ) -> None:
        self.reader = graph
        self.project_id = project_id
        self.access_scopes = access_scopes

    def find_paths(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        as_of_date: date | None = None,
        max_paths: int = 30,
    ) -> list[GraphPath]:
        return self.reader.find_paths(
            start_id,
            project_id=self.project_id,
            access_scopes=list(self.access_scopes),
            max_depth=max_depth,
            direction=direction,
            relationship_types=relationship_types,
            as_of_date=as_of_date,
            max_paths=max_paths,
        )


def _query_records(
    reader: RecordReader,
    *,
    project_id: str,
    access_scopes: list[str],
    record_ids: list[str] | None = None,
    record_types: list[str] | None = None,
    statuses: list[str] | None = None,
    as_of_date: date | None = None,
    metadata_filters: dict[str, object] | None = None,
    limit: int = 100,
) -> list[ProjectRecord]:
    projects = [project_id]
    if "public" in access_scopes and project_id != "PUBLIC-REFERENCE":
        projects.append("PUBLIC-REFERENCE")
    rows: dict[str, ProjectRecord] = {}
    for selected_project in projects:
        remaining = max(limit - len(rows), 0)
        if remaining == 0:
            break
        for record in reader.query_records(
            project_id=selected_project,
            access_scopes=access_scopes,
            record_ids=record_ids,
            record_types=record_types,
            statuses=statuses,
            as_of_date=as_of_date,
            metadata_filters=metadata_filters,
            limit=remaining,
        ):
            rows[record.record_id] = record
    return sorted(rows.values(), key=lambda record: record.record_id)[:limit]


class StoreBackedProjectTools(ProjectTools):
    """ProjectTools-compatible service whose reads remain online and authorization-scoped."""

    def __init__(
        self,
        records: RecordReader,
        search: SearchReader,
        graph: GraphReader,
        *,
        default_project_id: str,
        default_access_scopes: tuple[str, ...],
        deadline_proofs: Mapping[str, NativeDeadlineProof] | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.record_reader = records
        self.search_reader = search
        self.graph_reader = graph
        self.retriever = StoreBackedRetriever(search, reranker=reranker)
        self.__deadline_issuer = object()
        self.__deadline_proofs = {
            tool_name: proof._issued_for(self.__deadline_issuer)
            for tool_name, proof in (deadline_proofs or {}).items()
        }
        self.records = OnlineRecordView(
            records,
            project_id=default_project_id,
            access_scopes=default_access_scopes,
        )
        self.graph = DefaultScopedGraphView(
            graph,
            project_id=default_project_id,
            access_scopes=default_access_scopes,
        )

    def verified_tool_operation(
        self,
        tool_name: str,
        operation: Callable[[], Any],
    ) -> VerifiedToolOperation:
        proof = self.__deadline_proofs.get(tool_name)
        if proof is None or proof.tool_name != tool_name:
            raise ToolDeadlineUnavailable(f"no native deadline proof is available for {tool_name}")
        return VerifiedToolOperation._issued_for(
            operation=operation,
            proof=proof,
            issuer_identity=self.__deadline_issuer,
        )

    def issued_tool_operation(self, operation: object, tool_name: str) -> bool:
        if not isinstance(operation, VerifiedToolOperation):
            return False
        proof = self.__deadline_proofs.get(tool_name)
        return (
            operation.proof is proof
            and operation._was_issued_by(self.__deadline_issuer)
            and proof._was_issued_by(self.__deadline_issuer)
        )

    def _records(
        self,
        request: ToolRequest,
        *,
        record_ids: list[str] | None = None,
        record_types: list[str] | None = None,
        statuses: list[str] | None = None,
        as_of_date: date | None = None,
        metadata_filters: dict[str, object] | None = None,
        limit: int = 100,
    ) -> list[ProjectRecord]:
        return _query_records(
            self.record_reader,
            project_id=request.project_id,
            access_scopes=request.access_scopes,
            record_ids=record_ids,
            record_types=record_types,
            statuses=statuses,
            as_of_date=as_of_date,
            metadata_filters=metadata_filters,
            limit=limit,
        )

    def call(self, request: ToolRequest) -> ToolObservation:
        if request.tool_name not in ALLOWED_TOOLS:
            raise ValueError(f"Unknown tool: {request.tool_name}")
        if request.tool_name == "search_documents":
            return super().call(request)

        if request.tool_name == "get_records":
            record_ids = request.arguments.get("record_ids")
            if not isinstance(record_ids, list) or not record_ids:
                raise ValueError("get_records requires a non-empty record_ids list")
            return self._records_observation(
                request.tool_name,
                self._records(
                    request,
                    record_ids=[str(item) for item in record_ids],
                    as_of_date=request.arguments.get("as_of_date"),
                ),
            )

        if request.tool_name == "get_schedule_activity":
            activity_id = str(request.arguments.get("activity_id", ""))
            rows = self._records(
                request,
                record_ids=[activity_id],
                record_types=["schedule_activity"],
            )
            if not rows:
                raise ValueError(f"Unknown schedule activity: {activity_id}")
            return self._records_observation(request.tool_name, rows)

        if request.tool_name == "query_quality_records":
            requested_status = request.arguments.get("status")
            records = self._records(
                request,
                record_types=["inspection", "ncr"],
                statuses=[str(requested_status)] if requested_status else None,
                limit=500,
            )

            def quality_priority(record: ProjectRecord) -> tuple[int, str]:
                if record.record_type == "ncr" and record.status == "open":
                    return (0, record.record_id)
                if record.record_type == "inspection" and record.status == "rejected":
                    return (1, record.record_id)
                if record.status in {"open", "repair_required", "pending"}:
                    return (2, record.record_id)
                return (3 if record.record_type == "ncr" else 4, record.record_id)

            return self._records_observation(
                request.tool_name, sorted(records, key=quality_priority)
            )

        if request.tool_name == "compare_revisions":
            document_number = str(request.arguments.get("document_number", "S-204"))
            rows = self._records(
                request,
                record_types=["drawing"],
                metadata_filters={"document_number": document_number},
            )
            return self._records_observation(
                request.tool_name, sorted(rows, key=lambda item: item.revision)
            )

        start_id = str(request.arguments.get("start_id", ""))
        if not start_id:
            raise ValueError("find_graph_paths requires start_id")
        if not self._records(request, record_ids=[start_id], limit=1):
            raise PermissionError("Graph starting record is outside the permitted scope")
        paths = self.graph_reader.find_paths(
            start_id,
            project_id=request.project_id,
            access_scopes=request.access_scopes,
            max_depth=int(request.arguments.get("max_depth", 3)),
            direction=request.arguments.get("direction", "both"),
            relationship_types=set(request.arguments.get("relationship_types", [])) or None,
            as_of_date=request.arguments.get("as_of_date"),
            max_paths=30,
        )
        evidence_ids = list(dict.fromkeys(node.record_id for path in paths for node in path.nodes))
        records = self._records(request, record_ids=evidence_ids, limit=max(len(evidence_ids), 1))
        records_by_id = {record.record_id: record for record in records}
        visible_ids = [record_id for record_id in evidence_ids if record_id in records_by_id]
        return ToolObservation(
            tool_name=request.tool_name,
            success=True,
            summary=f"Found {len(paths)} bounded, provenance-backed path(s).",
            evidence_ids=visible_ids,
            citations=[self._citation(records_by_id[record_id]) for record_id in visible_ids],
            graph_paths=paths,
            data={"start_id": start_id, "max_depth": request.arguments.get("max_depth", 3)},
        )
