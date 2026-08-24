"""Typed data contracts shared by ingestion, retrieval, agents, evals, and notebooks."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DataOrigin = Literal["public_official", "synthetic_academic_demo"]
RouteName = Literal["rag", "graph_rag", "agentic_rag"]


class ProjectRecord(BaseModel):
    """One versioned project fact or document-like record."""

    record_id: str
    project_id: str
    record_type: str
    title: str
    content: str
    status: str
    revision: str
    effective_date: date
    data_origin: DataOrigin
    source_path: str
    source_url: str | None = None
    access_scopes: list[str] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    """A retrievable passage with enough metadata to cite its source."""

    chunk_id: str
    record_id: str
    project_id: str
    text: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    data_origin: DataOrigin
    source_path: str
    source_url: str | None = None
    access_scopes: list[str] = Field(min_length=1)
    effective_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    """A directed, provenance-backed project relationship."""

    relationship_id: str
    project_id: str
    source_id: str
    target_id: str
    relationship_type: str
    provenance: str
    method: str
    confidence: float = Field(ge=0, le=1)
    valid_from: date
    metadata: dict[str, Any] = Field(default_factory=dict)


class Corpus(BaseModel):
    """Portable representation of everything published to the three data stores."""

    records: list[ProjectRecord] = Field(default_factory=list)
    chunks: list[DocumentChunk] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

    @model_validator(mode="after")
    def relationships_are_resolvable(self) -> "Corpus":
        record_ids = {record.record_id for record in self.records}
        dangling = [
            link.relationship_id
            for link in self.relationships
            if link.source_id not in record_ids or link.target_id not in record_ids
        ]
        if dangling:
            raise ValueError(f"Dangling relationships: {', '.join(dangling[:5])}")
        return self


class GoldScenario(BaseModel):
    """A reviewer-facing question with expected route, tools, and evidence."""

    scenario_id: str
    title: str | None = None
    question: str
    expected_route: RouteName
    expected_evidence_ids: list[str] = Field(min_length=1)
    expected_tools: list[str] = Field(min_length=1)
    explanation: str | None = None
