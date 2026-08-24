"""Neo4j adapter for provenance-backed dependency paths."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from neo4j import GraphDatabase, Query

from civil_copilot.data.models import ProjectRecord, Relationship
from civil_copilot.graph.service import GraphEdge, GraphNode, GraphPath
from civil_copilot.stores.base import GraphWriteStats, WriteStats, model_fingerprint

SAFE_RELATION = re.compile(r"^[A-Z][A-Z0-9_]*$")
CONNECTION_TIMEOUT_SECONDS = 1.0
CONNECTION_ACQUISITION_TIMEOUT_SECONDS = 1.5
QUERY_TIMEOUT_SECONDS = 2.0
MAX_TRANSACTION_RETRY_SECONDS = 0.0
STORE_TIMEOUT_SECONDS = QUERY_TIMEOUT_SECONDS


class Neo4jGraphStore:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self.driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
            connection_timeout=CONNECTION_TIMEOUT_SECONDS,
            connection_acquisition_timeout=CONNECTION_ACQUISITION_TIMEOUT_SECONDS,
            max_transaction_retry_time=MAX_TRANSACTION_RETRY_SECONDS,
        )
        self.driver.verify_connectivity()
        self.initialize()

    def initialize(self) -> None:
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT project_record_id IF NOT EXISTS "
                "FOR (record:ProjectRecord) REQUIRE record.record_id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE INDEX project_record_project IF NOT EXISTS "
                "FOR (record:ProjectRecord) ON (record.project_id)"
            ).consume()

    def close(self) -> None:
        self.driver.close()

    def upsert_graph(
        self, records: list[ProjectRecord], relationships: list[Relationship]
    ) -> GraphWriteStats:
        with self.driver.session() as session:
            existing_nodes = {
                row["record_id"]: row["content_hash"]
                for row in session.run(
                    "MATCH (n:ProjectRecord) WHERE n.record_id IN $ids "
                    "RETURN n.record_id AS record_id, n.content_hash AS content_hash",
                    ids=[record.record_id for record in records],
                )
            }
            node_created = node_updated = node_unchanged = 0
            for record in records:
                fingerprint = model_fingerprint(record)
                if record.record_id not in existing_nodes:
                    node_created += 1
                elif existing_nodes[record.record_id] == fingerprint:
                    node_unchanged += 1
                    continue
                else:
                    node_updated += 1
                payload = record.model_dump(mode="json")
                session.run(
                    """
                    MERGE (n:ProjectRecord {record_id: $record_id})
                    SET n.project_id = $project_id,
                        n.record_type = $record_type,
                        n.title = $title,
                        n.status = $status,
                        n.revision = $revision,
                        n.effective_date = date($effective_date),
                        n.data_origin = $data_origin,
                        n.source_path = $source_path,
                        n.access_scopes = $access_scopes,
                        n.content_hash = $content_hash
                    """,
                    **payload,
                    content_hash=fingerprint,
                ).consume()

            existing_links = {
                row["relationship_id"]: row["content_hash"]
                for row in session.run(
                    "MATCH ()-[r]->() WHERE r.relationship_id IN $ids "
                    "RETURN r.relationship_id AS relationship_id, r.content_hash AS content_hash",
                    ids=[link.relationship_id for link in relationships],
                )
            }
            rel_created = rel_updated = rel_unchanged = 0
            for link in relationships:
                if not SAFE_RELATION.fullmatch(link.relationship_type):
                    raise ValueError(f"Unsafe relationship type: {link.relationship_type}")
                fingerprint = model_fingerprint(link)
                if link.relationship_id not in existing_links:
                    rel_created += 1
                elif existing_links[link.relationship_id] == fingerprint:
                    rel_unchanged += 1
                    continue
                else:
                    rel_updated += 1
                relation_pattern = (
                    f"(source)-[r:{link.relationship_type} "
                    "{relationship_id: $relationship_id}]->(target)"
                )
                session.run(
                    f"""
                    MATCH (source:ProjectRecord {{record_id: $source_id}})
                    MATCH (target:ProjectRecord {{record_id: $target_id}})
                    MERGE {relation_pattern}
                    SET r.project_id = $project_id,
                        r.provenance = $provenance,
                        r.method = $method,
                        r.confidence = $confidence,
                        r.valid_from = date($valid_from),
                        r.content_hash = $content_hash
                    """,  # noqa: S608 - relation type is allowlisted above
                    **link.model_dump(mode="json"),
                    content_hash=fingerprint,
                ).consume()

        return GraphWriteStats(
            WriteStats(node_created, node_updated, node_unchanged),
            WriteStats(rel_created, rel_updated, rel_unchanged),
        )

    def count_nodes(self, project_id: str | None = None) -> int:
        with self.driver.session() as session:
            if project_id:
                result = session.run(
                    Query(
                        "MATCH (n:ProjectRecord {project_id: $project_id}) "
                        "RETURN count(n) AS count",
                        timeout=STORE_TIMEOUT_SECONDS,
                    ),
                    project_id=project_id,
                ).single()
            else:
                result = session.run(
                    Query(
                        "MATCH (n:ProjectRecord) RETURN count(n) AS count",
                        timeout=STORE_TIMEOUT_SECONDS,
                    )
                ).single()
        return int(result["count"])

    def count_relationships(self, project_id: str | None = None) -> int:
        with self.driver.session() as session:
            if project_id:
                result = session.run(
                    "MATCH ()-[r {project_id: $project_id}]->() RETURN count(r) AS count",
                    project_id=project_id,
                ).single()
            else:
                result = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()
        return int(result["count"])

    def clear(self) -> None:
        with self.driver.session() as session:
            session.run("MATCH (n:ProjectRecord) DETACH DELETE n").consume()

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
    ) -> list[GraphPath]:
        """Return bounded paths with authorization and time predicates in Cypher."""

        if not 1 <= max_depth <= 5:
            raise ValueError("max_depth must be between 1 and 5")
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError(f"Unknown graph direction: {direction}")
        if not access_scopes or max_paths < 1:
            return []
        for relationship_type in relationship_types or set():
            if not SAFE_RELATION.fullmatch(relationship_type):
                raise ValueError(f"Unsafe relationship type: {relationship_type}")

        path_pattern = {
            "outgoing": f"(start)-[rels*1..{max_depth}]->(end)",
            "incoming": f"(start)<-[rels*1..{max_depth}]-(end)",
            "both": f"(start)-[rels*1..{max_depth}]-(end)",
        }[direction]
        allowed_project_ids = [project_id]
        if "public" in access_scopes and project_id != "PUBLIC-REFERENCE":
            allowed_project_ids.append("PUBLIC-REFERENCE")
        query = f"""
        MATCH (start:ProjectRecord {{record_id: $start_id, project_id: $project_id}})
        MATCH path={path_pattern}
        WHERE all(node IN nodes(path) WHERE
            node.project_id IN $allowed_project_ids
            AND any(scope IN node.access_scopes WHERE scope IN $access_scopes)
            AND ($as_of_date IS NULL OR node.effective_date <= date($as_of_date))
        )
        AND (
            size($relationship_types) = 0
            OR all(rel IN relationships(path) WHERE type(rel) IN $relationship_types)
        )
        AND (
            $as_of_date IS NULL
            OR all(rel IN relationships(path) WHERE rel.valid_from <= date($as_of_date))
        )
        RETURN
            [node IN nodes(path) | {{
                record_id: node.record_id,
                record_type: node.record_type,
                title: node.title,
                status: node.status,
                data_origin: node.data_origin,
                source_path: node.source_path
            }}] AS nodes,
            [rel IN relationships(path) | {{
                relationship_id: rel.relationship_id,
                source_id: startNode(rel).record_id,
                target_id: endNode(rel).record_id,
                relationship_type: type(rel),
                provenance: rel.provenance,
                method: rel.method,
                confidence: rel.confidence,
                valid_from: rel.valid_from
            }}] AS edges
        LIMIT $max_paths
        """
        parameters = {
            "start_id": start_id,
            "project_id": project_id,
            "allowed_project_ids": allowed_project_ids,
            "access_scopes": access_scopes,
            "relationship_types": sorted(relationship_types or set()),
            "as_of_date": as_of_date.isoformat() if as_of_date else None,
            "max_paths": min(max_paths, 100),
        }
        with self.driver.session() as session:
            rows = session.run(
                Query(query, timeout=STORE_TIMEOUT_SECONDS),
                **parameters,
            )
            paths = []
            for row in rows:
                nodes = [GraphNode.model_validate(node) for node in row["nodes"]]
                edges = []
                for edge in row["edges"]:
                    payload = dict(edge)
                    valid_from = payload.get("valid_from")
                    if hasattr(valid_from, "to_native"):
                        payload["valid_from"] = valid_from.to_native()
                    edges.append(GraphEdge.model_validate(payload))
                if nodes:
                    paths.append(
                        GraphPath(
                            start_id=start_id,
                            end_id=nodes[-1].record_id,
                            nodes=nodes,
                            edges=edges,
                        )
                    )
            return paths
