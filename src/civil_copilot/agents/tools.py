"""Allowlisted, read-only tools that return structured observations and citations."""

from __future__ import annotations

import re
from time import monotonic
from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from civil_copilot.agents.tool_contracts import (
    AssessStandardEvidenceInput,
    CalculateInput,
    CompareRevisionsInput,
    GetRecordInput,
    GraphQueryInput,
    ReadOnlyToolObservation,
    ScheduleAnalysisInput,
    SearchDocumentsInput,
)
from civil_copilot.agents.tool_runtime import AgentToolContext
from civil_copilot.data.models import ProjectRecord
from civil_copilot.graph.service import GraphPath, ProjectGraphService
from civil_copilot.retrieval.answer import Citation
from civil_copilot.retrieval.evidence import EvidenceItem
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.retrieval.query import QueryContext
from civil_copilot.revision.service import compare_revision_records
from civil_copilot.standards.service import StandardsEvidenceService

IDENTIFIER = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
ALLOWED_TOOLS = {
    "search_documents",
    "get_records",
    "find_graph_paths",
    "compare_revisions",
    "get_schedule_activity",
    "query_quality_records",
}


class ToolRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    project_id: str
    access_scopes: list[str]


class ToolObservation(BaseModel):
    tool_name: str
    success: bool
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    graph_paths: list[GraphPath] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class ProjectTools:
    def __init__(
        self,
        records: list[ProjectRecord],
        retriever: HybridRetriever,
        graph: ProjectGraphService,
    ) -> None:
        self.records = {record.record_id: record for record in records}
        self.retriever = retriever
        self.graph = graph

    @staticmethod
    def _permitted(record: ProjectRecord, request: ToolRequest) -> bool:
        return record.project_id in {request.project_id, "PUBLIC-REFERENCE"} and bool(
            set(record.access_scopes) & set(request.access_scopes)
        )

    @staticmethod
    def _citation(record: ProjectRecord) -> Citation:
        return Citation(
            record_id=record.record_id,
            chunk_id=f"{record.record_id}-record",
            title=record.title,
            source_path=record.source_path,
            source_url=record.source_url,
            data_origin=record.data_origin,
        )

    def _records_observation(self, tool_name: str, records: list[ProjectRecord]) -> ToolObservation:
        evidence = [
            EvidenceItem(
                chunk={
                    "chunk_id": f"{record.record_id}-record",
                    "record_id": record.record_id,
                    "project_id": record.project_id,
                    "text": (
                        f"{record.title}. Record {record.record_id}; type {record.record_type}; "
                        f"status {record.status}; revision {record.revision}; effective "
                        f"{record.effective_date.isoformat()}. {record.content}"
                    ),
                    "ordinal": 0,
                    "data_origin": record.data_origin,
                    "source_path": record.source_path,
                    "source_url": record.source_url,
                    "access_scopes": record.access_scopes,
                    "metadata": {
                        "record_type": record.record_type,
                        "status": record.status,
                        "revision": record.revision,
                        **record.metadata,
                    },
                },
                fused_score=1.0,
                rerank_score=1.0,
                exact_id_match=False,
                reasons=["read-only structured record tool"],
            )
            for record in records
        ]
        return ToolObservation(
            tool_name=tool_name,
            success=True,
            summary=f"Retrieved {len(records)} permitted project record(s).",
            evidence_ids=[record.record_id for record in records],
            citations=[self._citation(record) for record in records],
            evidence=evidence,
            data={"records": [record.model_dump(mode="json") for record in records]},
        )

    def call(self, request: ToolRequest) -> ToolObservation:
        if request.tool_name not in ALLOWED_TOOLS:
            raise ValueError(f"Unknown tool: {request.tool_name}")

        if request.tool_name == "search_documents":
            question = str(request.arguments.get("question", "")).strip()
            if not question:
                raise ValueError("search_documents requires question")
            packet = self.retriever.retrieve(
                QueryContext(
                    question=question,
                    project_id=request.project_id,
                    access_scopes=request.access_scopes,
                    top_k=int(request.arguments.get("top_k", 6)),
                    as_of_date=request.arguments.get("as_of_date"),
                    filters=dict(request.arguments.get("filters", {})),
                )
            )
            return ToolObservation(
                tool_name=request.tool_name,
                success=True,
                summary=f"Retrieved and reranked {len(packet.evidence)} passage(s).",
                evidence_ids=[item.chunk.record_id for item in packet.evidence],
                citations=[
                    Citation(
                        record_id=item.chunk.record_id,
                        chunk_id=item.chunk.chunk_id,
                        title=item.chunk.text.split(".", 1)[0],
                        source_path=item.chunk.source_path,
                        source_url=item.chunk.source_url,
                        data_origin=item.chunk.data_origin,
                    )
                    for item in packet.evidence
                ],
                evidence=packet.evidence,
                data={"retrieval_trace": packet.retrieval_trace.model_dump()},
            )

        if request.tool_name == "get_records":
            record_ids = request.arguments.get("record_ids")
            if not isinstance(record_ids, list) or not record_ids:
                raise ValueError("get_records requires a non-empty record_ids list")
            records = [
                self.records[record_id] for record_id in record_ids if record_id in self.records
            ]
            if any(not self._permitted(record, request) for record in records):
                raise PermissionError(
                    "One or more requested records are outside the permitted scope"
                )
            return self._records_observation(request.tool_name, records)

        if request.tool_name == "get_schedule_activity":
            activity_id = str(request.arguments.get("activity_id", ""))
            record = self.records.get(activity_id)
            if not record or record.record_type != "schedule_activity":
                raise ValueError(f"Unknown schedule activity: {activity_id}")
            if not self._permitted(record, request):
                raise PermissionError("Schedule activity is outside the permitted scope")
            return self._records_observation(request.tool_name, [record])

        if request.tool_name == "query_quality_records":
            requested_status = request.arguments.get("status")
            records = [
                record
                for record in self.records.values()
                if record.record_type in {"inspection", "ncr"}
                and (not requested_status or record.status == requested_status)
                and self._permitted(record, request)
            ]

            def quality_priority(record: ProjectRecord) -> tuple[int, str]:
                if record.record_type == "ncr" and record.status == "open":
                    return (0, record.record_id)
                if record.record_type == "inspection" and record.status == "rejected":
                    return (1, record.record_id)
                if record.status in {"open", "repair_required", "pending"}:
                    return (2, record.record_id)
                if record.record_type == "ncr":
                    return (3, record.record_id)
                return (4, record.record_id)

            return self._records_observation(
                request.tool_name, sorted(records, key=quality_priority)
            )

        if request.tool_name == "compare_revisions":
            document_number = str(request.arguments.get("document_number", "S-204"))
            records = [
                record
                for record in self.records.values()
                if record.record_type == "drawing"
                and record.metadata.get("document_number") == document_number
                and self._permitted(record, request)
            ]
            return self._records_observation(
                request.tool_name, sorted(records, key=lambda item: item.revision)
            )

        start_id = str(request.arguments.get("start_id", ""))
        if not start_id:
            raise ValueError("find_graph_paths requires start_id")
        record = self.records.get(start_id)
        if not record or not self._permitted(record, request):
            raise PermissionError("Graph starting record is outside the permitted scope")
        paths = self.graph.find_paths(
            start_id,
            max_depth=int(request.arguments.get("max_depth", 3)),
            direction=request.arguments.get("direction", "both"),
            relationship_types=set(request.arguments.get("relationship_types", [])) or None,
        )
        visible_paths = [
            path
            for path in paths
            if all(self._permitted(self.records[node.record_id], request) for node in path.nodes)
        ]
        evidence_ids = list(
            dict.fromkeys(node.record_id for path in visible_paths for node in path.nodes)
        )
        return ToolObservation(
            tool_name=request.tool_name,
            success=True,
            summary=f"Found {len(visible_paths)} bounded, provenance-backed path(s).",
            evidence_ids=evidence_ids,
            citations=[self._citation(self.records[record_id]) for record_id in evidence_ids],
            graph_paths=visible_paths,
            data={"start_id": start_id, "max_depth": request.arguments.get("max_depth", 3)},
        )


def _context(runtime: ToolRuntime[AgentToolContext]) -> AgentToolContext:
    if runtime.context is None:
        raise RuntimeError("agent tool runtime context is required")
    return runtime.context


def _request(
    runtime: ToolRuntime[AgentToolContext], tool_name: str, arguments: dict[str, Any]
) -> ToolRequest:
    context = _context(runtime)
    return ToolRequest(
        tool_name=tool_name,
        arguments=arguments,
        project_id=context.project_id,
        access_scopes=list(context.access_scopes),
    )


def _structured(observation: ToolObservation, started: float) -> dict[str, Any]:
    bounded_evidence = [
        item.model_copy(
            update={"chunk": item.chunk.model_copy(update={"text": item.chunk.text[:1200]})}
        )
        for item in observation.evidence[:20]
    ]
    return ReadOnlyToolObservation(
        tool_name=observation.tool_name,
        status="ok" if observation.success else "error",
        summary=observation.summary,
        data=observation.data,
        source_ids=observation.evidence_ids,
        citations=observation.citations[:20],
        evidence=bounded_evidence,
        graph_paths=observation.graph_paths[:20],
        confidence=1.0 if observation.success else None,
        elapsed_ms=(monotonic() - started) * 1000,
    ).model_dump(mode="json")


def _emit_progress(runtime: ToolRuntime[AgentToolContext], tool_name: str, phase: str) -> None:
    runtime.stream_writer({"phase": phase, "tool_name": tool_name})


@tool(
    "search_documents",
    args_schema=SearchDocumentsInput,
    description=(
        "Search permitted project documents with bounded filters. Use for clauses, RFIs, "
        "submittals, minutes, and requirements; returns cited evidence, never an answer."
    ),
)
def search_documents(
    query: str,
    filters: Any,
    top_k: int,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "search_documents", "tool_started")
    parsed_filters = (
        filters
        if hasattr(filters, "as_retrieval_filters")
        else SearchDocumentsInput(query=query, filters=filters, top_k=top_k).filters
    )
    observation = _context(runtime).project_tools.call(
        _request(
            runtime,
            "search_documents",
            {
                "question": query,
                "top_k": top_k,
                "filters": parsed_filters.as_retrieval_filters(),
                "as_of_date": parsed_filters.as_of_date,
            },
        )
    )
    return _structured(observation, started)


@tool(
    "get_record",
    args_schema=GetRecordInput,
    description=(
        "Read one permitted authoritative project record by type and identifier as of a date."
    ),
)
def get_record(
    record_type: str,
    record_id: str,
    as_of_date: Any,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "get_record", "tool_started")
    observation = _context(runtime).project_tools.call(
        _request(runtime, "get_records", {"record_ids": [record_id]})
    )
    records = observation.data.get("records", [])
    if not records or records[0].get("record_type") != record_type:
        raise ValueError("record is unavailable in the requested type and permitted scope")
    if as_of_date and str(records[0].get("effective_date")) > str(as_of_date):
        raise ValueError("record is not effective as of the requested date")
    observation = observation.model_copy(update={"tool_name": "get_record"})
    return _structured(observation, started)


@tool(
    "query_project_graph",
    args_schema=GraphQueryInput,
    description=(
        "Follow bounded, provenance-backed permitted project relationships from one record."
    ),
)
def query_project_graph(
    start_id: str,
    relationship_types: list[str],
    max_depth: int,
    direction: str,
    as_of_date: Any,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "query_project_graph", "tool_started")
    observation = (
        _context(runtime)
        .project_tools.call(
            _request(
                runtime,
                "find_graph_paths",
                {
                    "start_id": start_id,
                    "relationship_types": relationship_types,
                    "max_depth": max_depth,
                    "direction": direction,
                    "as_of_date": as_of_date,
                },
            )
        )
        .model_copy(update={"tool_name": "query_project_graph"})
    )
    return _structured(observation, started)


@tool(
    "analyze_schedule",
    args_schema=ScheduleAnalysisInput,
    description=(
        "Calculate a read-only schedule delay scenario for permitted activities and report sources."
    ),
)
def analyze_schedule(
    activity_ids: list[str],
    delay_days: int,
    as_of_date: Any,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "analyze_schedule", "tool_started")
    context = _context(runtime)
    authorized = context.project_tools.call(
        _request(
            runtime,
            "get_records",
            {"record_ids": activity_ids, "as_of_date": as_of_date},
        )
    )
    if set(authorized.evidence_ids) != set(activity_ids):
        raise PermissionError("One or more schedule activities are outside the permitted scope")
    result = context.schedule_service.analyze(
        activity_ids,
        delay_days=delay_days,
        as_of_date=as_of_date,
    )
    return ReadOnlyToolObservation(
        tool_name="analyze_schedule",
        status="ok",
        summary=f"Analyzed {len(result.activity_ids)} permitted schedule activity record(s).",
        data=result.model_dump(mode="json"),
        source_ids=result.source_ids,
        confidence=1.0,
        elapsed_ms=(monotonic() - started) * 1000,
    ).model_dump(mode="json")


@tool(
    "compare_revisions",
    args_schema=CompareRevisionsInput,
    description="Compare two permitted controlled revisions of one document.",
)
def compare_revisions(
    document_id: str,
    from_revision: str,
    to_revision: str,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "compare_revisions", "tool_started")
    observation = _context(runtime).project_tools.call(
        _request(runtime, "compare_revisions", {"document_number": document_id})
    )
    records = [
        record
        for record in observation.data.get("records", [])
        if str(record.get("revision")) in {from_revision, to_revision}
    ]
    if len({str(record.get("revision")) for record in records}) != 2:
        raise ValueError("both requested permitted revisions are required")
    comparison = compare_revision_records(
        [ProjectRecord.model_validate(record) for record in records],
        document_id=document_id,
        from_revision=from_revision,
        to_revision=to_revision,
    )
    allowed_ids = {record["record_id"] for record in records}
    observation = observation.model_copy(
        update={
            "summary": comparison.summary,
            "evidence_ids": [item for item in observation.evidence_ids if item in allowed_ids],
            "citations": [item for item in observation.citations if item.record_id in allowed_ids],
            "evidence": [
                item for item in observation.evidence if item.chunk.record_id in allowed_ids
            ],
            "data": {
                "records": records,
                "comparison": comparison.model_dump(mode="json"),
            },
        }
    )
    return _structured(observation, started)


@tool(
    "calculate",
    args_schema=CalculateInput,
    description="Evaluate bounded deterministic arithmetic without an LLM or code execution.",
)
def calculate(expression: str, runtime: ToolRuntime[AgentToolContext]) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "calculate", "tool_started")
    result = _context(runtime).calculation_service.calculate(expression)
    return ReadOnlyToolObservation(
        tool_name="calculate",
        status="ok",
        summary="Completed deterministic arithmetic.",
        data=result.model_dump(mode="json"),
        confidence=1.0,
        elapsed_ms=(monotonic() - started) * 1000,
    ).model_dump(mode="json")


@tool(
    "assess_standard_evidence",
    args_schema=AssessStandardEvidenceInput,
    description=(
        "Compare permitted project records with an indexed official BIS public preview using a "
        "bounded evidence checklist. Use for IS 800 project-practice questions. Reports "
        "Evidenced, Not evidenced, or Needs review; never certifies compliance."
    ),
)
def assess_standard_evidence(
    standard: str,
    runtime: ToolRuntime[AgentToolContext],
) -> dict[str, Any]:
    started = monotonic()
    _emit_progress(runtime, "assess_standard_evidence", "tool_started")
    context = _context(runtime)
    report = StandardsEvidenceService(
        context.project_tools,
        project_id=context.project_id,
        access_scopes=context.access_scopes,
    ).assess(standard)
    serialized_citations = list(
        dict.fromkeys(
            citation.model_dump_json()
            for row in report.rows
            for citation in [*row.project_evidence, row.official_source]
        )
    )
    return ReadOnlyToolObservation(
        tool_name="assess_standard_evidence",
        status="ok",
        summary=(
            f"Reviewed {len(report.rows)} indexed {report.standard} preview topics against "
            "permitted project evidence."
        ),
        data={"report": report.model_dump(mode="json")},
        source_ids=report.source_ids,
        citations=[Citation.model_validate_json(item) for item in serialized_citations][:20],
        confidence=1.0,
        elapsed_ms=(monotonic() - started) * 1000,
    ).model_dump(mode="json")


def identifiers_in(question: str) -> list[str]:
    return sorted(set(IDENTIFIER.findall(question.upper())))
