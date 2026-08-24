"""Typed model-visible tool inputs and model-inspected read-only observations."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from civil_copilot.graph.service import GraphPath
from civil_copilot.retrieval.answer import Citation
from civil_copilot.retrieval.evidence import EvidenceItem

ProjectRecordType = Literal[
    "calculation",
    "code_reference",
    "code_register",
    "drawing",
    "handover",
    "inspection",
    "material_certificate",
    "meeting_minute",
    "ncr",
    "piece",
    "project",
    "purchase_order",
    "rfi",
    "schedule_activity",
    "specification",
    "weld",
]

ProjectRelationshipType = Literal[
    "ADOPTS",
    "AFFECTS",
    "CHANGES_OR_CLARIFIES",
    "CORRECTED_BY",
    "DEFINED_BY",
    "DELIVERS",
    "DEPENDS_ON",
    "DERIVED_FROM",
    "DISCUSSES",
    "FULFILLED_BY",
    "GOVERNED_BY",
    "HANDOVER_EVIDENCE_FOR",
    "HAS_REGISTER",
    "IMPLEMENTS",
    "INSTALLED_BY",
    "JOINS",
    "RAISES",
    "REFERENCES",
    "REVISES",
    "SUPPORTS",
    "TESTS",
    "USED_IN",
]


class DocumentSearchFilters(BaseModel):
    record_type: str | None = None
    status: str | None = None
    revision: str | None = None
    discipline: str | None = None
    location: str | None = None
    as_of_date: date | None = None

    def as_retrieval_filters(self) -> dict[str, str]:
        return {
            key: str(value)
            for key, value in self.model_dump(exclude_none=True).items()
            if key != "as_of_date"
        }


class SearchDocumentsInput(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    filters: DocumentSearchFilters = Field(default_factory=DocumentSearchFilters)
    top_k: int = Field(default=6, ge=1, le=20)


class GetRecordInput(BaseModel):
    record_type: ProjectRecordType = Field(
        description=(
            "Canonical project record type. ACT identifiers are schedule_activity records."
        )
    )
    record_id: str = Field(min_length=2, max_length=160)
    as_of_date: date | None = None

    @field_validator("record_type", mode="before")
    @classmethod
    def normalize_record_type(cls, value: Any) -> Any:
        normalized = str(value).strip().lower().replace(" ", "_")
        return {
            "activity": "schedule_activity",
            "schedule": "schedule_activity",
            "certificate": "material_certificate",
            "material_cert": "material_certificate",
        }.get(normalized, normalized)


class GraphQueryInput(BaseModel):
    start_id: str = Field(min_length=2, max_length=160)
    relationship_types: list[ProjectRelationshipType] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "Optional canonical relationship filters. Use an empty list to inspect all "
            "permitted relationships."
        ),
    )
    max_depth: int = Field(default=3, ge=1, le=5)
    direction: Literal["outgoing", "incoming", "both"] = "both"
    as_of_date: date | None = None

    @field_validator("relationship_types", mode="before")
    @classmethod
    def normalize_relationship_types(cls, values: Any) -> Any:
        if values is None:
            return []
        aliases = {
            "RELATED_TO": "AFFECTS",
            "BLOCKED_BY": "AFFECTS",
            "BLOCKS": "AFFECTS",
            "REFERENCED_BY": "REFERENCES",
        }
        normalized = [
            aliases.get(str(value).strip().upper(), str(value).strip().upper()) for value in values
        ]
        return list(dict.fromkeys(normalized))


class ScheduleAnalysisInput(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=20)
    delay_days: int = Field(default=0, ge=0, le=3650)
    as_of_date: date | None = None


class CompareRevisionsInput(BaseModel):
    document_id: str = Field(min_length=2, max_length=160)
    from_revision: str = Field(min_length=1, max_length=40)
    to_revision: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def revisions_must_differ(self) -> CompareRevisionsInput:
        if self.from_revision == self.to_revision:
            raise ValueError("from_revision and to_revision must differ")
        return self


class CalculateInput(BaseModel):
    expression: str = Field(min_length=1, max_length=200)


class AssessStandardEvidenceInput(BaseModel):
    standard: Literal["IS 800:2007"] = Field(
        description="Indexed Indian Standard public-preview checklist to compare with the project."
    )


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ReadOnlyToolObservation(BaseModel):
    tool_name: str
    status: Literal["ok", "partial", "denied", "error"]
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=20)
    graph_paths: list[GraphPath] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    errors: list[ToolError] = Field(default_factory=list)
    elapsed_ms: float = Field(default=0, ge=0)
