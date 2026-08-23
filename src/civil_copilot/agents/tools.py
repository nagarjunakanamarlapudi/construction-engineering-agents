"""Allowlisted, read-only tools that return structured observations and citations."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from civil_copilot.data.models import ProjectRecord
from civil_copilot.graph.service import GraphPath, ProjectGraphService
from civil_copilot.retrieval.answer import Citation
from civil_copilot.retrieval.evidence import EvidenceItem
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.retrieval.query import QueryContext

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


def identifiers_in(question: str) -> list[str]:
    return sorted(set(IDENTIFIER.findall(question.upper())))
