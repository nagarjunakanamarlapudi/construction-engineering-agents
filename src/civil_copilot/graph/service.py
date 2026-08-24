"""Bounded, provenance-preserving project graph traversal."""

from __future__ import annotations

from collections import deque
from datetime import date
from typing import Literal

import networkx as nx
from pydantic import BaseModel, Field

from civil_copilot.data.models import ProjectRecord, Relationship


class GraphNode(BaseModel):
    record_id: str
    record_type: str
    title: str
    status: str
    data_origin: str
    source_path: str


class GraphEdge(BaseModel):
    relationship_id: str
    source_id: str
    target_id: str
    relationship_type: str
    provenance: str
    confidence: float
    method: str | None = None
    valid_from: date | None = None


class GraphPath(BaseModel):
    start_id: str
    end_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge] = Field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.edges)


class ProjectGraphService:
    def __init__(self, records: list[ProjectRecord], relationships: list[Relationship]) -> None:
        self.records = {record.record_id: record for record in records}
        self.graph = nx.MultiDiGraph()
        for record in records:
            self.graph.add_node(record.record_id)
        for link in relationships:
            self.graph.add_edge(
                link.source_id,
                link.target_id,
                key=link.relationship_id,
                relationship=link,
            )

    def _node(self, record_id: str) -> GraphNode:
        record = self.records[record_id]
        return GraphNode(
            record_id=record.record_id,
            record_type=record.record_type,
            title=record.title,
            status=record.status,
            data_origin=record.data_origin,
            source_path=record.source_path,
        )

    @staticmethod
    def _edge(link: Relationship) -> GraphEdge:
        return GraphEdge(
            relationship_id=link.relationship_id,
            source_id=link.source_id,
            target_id=link.target_id,
            relationship_type=link.relationship_type,
            provenance=link.provenance,
            confidence=link.confidence,
            method=link.method,
            valid_from=link.valid_from,
        )

    def find_paths(
        self,
        start_id: str,
        *,
        max_depth: int = 3,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        relationship_types: set[str] | None = None,
        max_paths: int = 30,
    ) -> list[GraphPath]:
        if not 1 <= max_depth <= 5:
            raise ValueError("max_depth must be between 1 and 5")
        if start_id not in self.records:
            raise KeyError(f"Unknown graph record: {start_id}")

        queue: deque[tuple[str, list[str], list[GraphEdge]]] = deque([(start_id, [start_id], [])])
        paths: list[GraphPath] = []
        while queue and len(paths) < max_paths:
            current, node_ids, edges = queue.popleft()
            if len(edges) >= max_depth:
                continue
            candidates: list[tuple[str, Relationship]] = []
            if direction in {"outgoing", "both"}:
                for _source, target, _key, data in self.graph.out_edges(
                    current, keys=True, data=True
                ):
                    candidates.append((target, data["relationship"]))
            if direction in {"incoming", "both"}:
                for source, _target, _key, data in self.graph.in_edges(
                    current, keys=True, data=True
                ):
                    candidates.append((source, data["relationship"]))

            for neighbor, link in sorted(
                candidates,
                key=lambda item: (item[1].relationship_type, item[0], item[1].relationship_id),
            ):
                if neighbor in node_ids:
                    continue
                if relationship_types and link.relationship_type not in relationship_types:
                    continue
                next_nodes = [*node_ids, neighbor]
                next_edges = [*edges, self._edge(link)]
                paths.append(
                    GraphPath(
                        start_id=start_id,
                        end_id=neighbor,
                        nodes=[self._node(record_id) for record_id in next_nodes],
                        edges=next_edges,
                    )
                )
                queue.append((neighbor, next_nodes, next_edges))
                if len(paths) >= max_paths:
                    break
        return paths
