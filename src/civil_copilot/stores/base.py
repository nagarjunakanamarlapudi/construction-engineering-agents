"""Store protocols plus fast in-memory implementations for tests and notebooks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal, Protocol

from civil_copilot.data.models import DocumentChunk, ProjectRecord, Relationship

if TYPE_CHECKING:
    from civil_copilot.graph.service import GraphPath
    from civil_copilot.retrieval.evidence import HybridCandidate


def model_fingerprint(model: ProjectRecord | DocumentChunk | Relationship) -> str:
    """Hash canonical model JSON for deterministic idempotency checks."""

    return hashlib.sha256(model.model_dump_json().encode()).hexdigest()


@dataclass(frozen=True)
class WriteStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged


@dataclass(frozen=True)
class GraphWriteStats:
    nodes: WriteStats
    relationships: WriteStats


class RecordStore(Protocol):
    def upsert_records(self, records: list[ProjectRecord]) -> WriteStats: ...

    def count(self) -> int: ...


class RecordReader(Protocol):
    def query_records(
        self,
        *,
        project_id: str,
        access_scopes: list[str],
        record_ids: list[str] | None = None,
        record_types: list[str] | None = None,
        statuses: list[str] | None = None,
        as_of_date: date | None = None,
        metadata_filters: dict[str, object] | None = None,
        limit: int = 100,
    ) -> list[ProjectRecord]: ...


class SearchStore(Protocol):
    def upsert_chunks(self, chunks: list[DocumentChunk]) -> WriteStats: ...

    def count(self) -> int: ...


class SearchReader(Protocol):
    def search_hybrid(
        self,
        *,
        query: str,
        project_id: str,
        access_scopes: list[str],
        metadata_filters: dict[str, object] | None = None,
        as_of_date: date | None = None,
        limit: int = 20,
    ) -> list[HybridCandidate]: ...


class GraphStore(Protocol):
    def upsert_graph(
        self, records: list[ProjectRecord], relationships: list[Relationship]
    ) -> GraphWriteStats: ...


class GraphReader(Protocol):
    def find_paths(
        self,
        start_id: str,
        *,
        project_id: str,
        access_scopes: list[str],
        max_depth: int = 3,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        relationship_types: set[str] | None = None,
        as_of_date: date | None = None,
        max_paths: int = 30,
    ) -> list[GraphPath]: ...


class InMemoryRecordStore:
    def __init__(self) -> None:
        self.records: dict[str, ProjectRecord] = {}

    def upsert_records(self, records: list[ProjectRecord]) -> WriteStats:
        created = updated = unchanged = 0
        for record in records:
            current = self.records.get(record.record_id)
            if current is None:
                created += 1
            elif model_fingerprint(current) == model_fingerprint(record):
                unchanged += 1
            else:
                updated += 1
            self.records[record.record_id] = record
        return WriteStats(created, updated, unchanged)

    def count(self) -> int:
        return len(self.records)

    def query_records(
        self,
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
        if not access_scopes or limit < 1:
            return []
        permitted_scopes = set(access_scopes)
        metadata_filters = metadata_filters or {}
        visible = (
            record
            for record in self.records.values()
            if record.project_id == project_id
            and bool(permitted_scopes & set(record.access_scopes))
            and (not record_ids or record.record_id in record_ids)
            and (not record_types or record.record_type in record_types)
            and (not statuses or record.status in statuses)
            and (as_of_date is None or record.effective_date <= as_of_date)
            and all(record.metadata.get(key) == value for key, value in metadata_filters.items())
        )
        return sorted(visible, key=lambda record: record.record_id)[:limit]


class InMemorySearchStore:
    def __init__(self) -> None:
        self.chunks: dict[str, DocumentChunk] = {}

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> WriteStats:
        created = updated = unchanged = 0
        for chunk in chunks:
            current = self.chunks.get(chunk.chunk_id)
            if current is None:
                created += 1
            elif model_fingerprint(current) == model_fingerprint(chunk):
                unchanged += 1
            else:
                updated += 1
            self.chunks[chunk.chunk_id] = chunk
        return WriteStats(created, updated, unchanged)

    def count(self) -> int:
        return len(self.chunks)


class InMemoryGraphStore:
    def __init__(self) -> None:
        self.nodes: dict[str, ProjectRecord] = {}
        self.relationships: dict[str, Relationship] = {}

    def upsert_graph(
        self, records: list[ProjectRecord], relationships: list[Relationship]
    ) -> GraphWriteStats:
        node_store = InMemoryRecordStore()
        node_store.records = self.nodes
        node_stats = node_store.upsert_records(records)
        self.nodes = node_store.records

        created = updated = unchanged = 0
        for link in relationships:
            current = self.relationships.get(link.relationship_id)
            if current is None:
                created += 1
            elif model_fingerprint(current) == model_fingerprint(link):
                unchanged += 1
            else:
                updated += 1
            self.relationships[link.relationship_id] = link
        return GraphWriteStats(node_stats, WriteStats(created, updated, unchanged))

    def count_nodes(self, project_id: str | None = None) -> int:
        if project_id is None:
            return len(self.nodes)
        return sum(record.project_id == project_id for record in self.nodes.values())

    def count_relationships(self, project_id: str | None = None) -> int:
        if project_id is None:
            return len(self.relationships)
        return sum(link.project_id == project_id for link in self.relationships.values())
