"""Validate once, then publish the same corpus to all purpose-specific stores."""

from __future__ import annotations

from dataclasses import dataclass

from civil_copilot.data.models import DocumentChunk, ProjectRecord, Relationship
from civil_copilot.stores.base import GraphStore, RecordStore, SearchStore, WriteStats


@dataclass(frozen=True)
class IngestionReport:
    records: WriteStats
    chunks: WriteStats
    graph_nodes: WriteStats
    relationships: WriteStats


class IngestionService:
    def __init__(self, records: RecordStore, search: SearchStore, graph: GraphStore) -> None:
        self.records = records
        self.search = search
        self.graph = graph

    def ingest(
        self,
        records: list[ProjectRecord],
        chunks: list[DocumentChunk],
        relationships: list[Relationship],
    ) -> IngestionReport:
        record_ids = {record.record_id for record in records}
        dangling = [
            link
            for link in relationships
            if link.source_id not in record_ids or link.target_id not in record_ids
        ]
        if dangling:
            first = dangling[0]
            raise ValueError(
                f"Relationship {first.relationship_id} references missing record "
                f"{first.source_id if first.source_id not in record_ids else first.target_id}"
            )
        chunk_record_ids = {chunk.record_id for chunk in chunks}
        missing_chunk_sources = sorted(chunk_record_ids - record_ids)
        if missing_chunk_sources:
            raise ValueError(f"Chunks reference missing records: {missing_chunk_sources[:5]}")

        records_by_id = {record.record_id: record for record in records}
        publishable_chunks = [
            chunk
            if chunk.effective_date is not None
            else chunk.model_copy(
                update={"effective_date": records_by_id[chunk.record_id].effective_date}
            )
            for chunk in chunks
        ]

        record_stats = self.records.upsert_records(records)
        chunk_stats = self.search.upsert_chunks(publishable_chunks)
        graph_stats = self.graph.upsert_graph(records, relationships)
        return IngestionReport(
            records=record_stats,
            chunks=chunk_stats,
            graph_nodes=graph_stats.nodes,
            relationships=graph_stats.relationships,
        )
