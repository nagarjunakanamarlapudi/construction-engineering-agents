"""Store protocols plus fast in-memory implementations for tests and notebooks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from civil_copilot.data.models import DocumentChunk, ProjectRecord, Relationship


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


class SearchStore(Protocol):
    def upsert_chunks(self, chunks: list[DocumentChunk]) -> WriteStats: ...

    def count(self) -> int: ...


class GraphStore(Protocol):
    def upsert_graph(
        self, records: list[ProjectRecord], relationships: list[Relationship]
    ) -> GraphWriteStats: ...


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
