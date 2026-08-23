"""Neo4j adapter for provenance-backed dependency paths."""

from __future__ import annotations

import re

from neo4j import GraphDatabase

from civil_copilot.data.models import ProjectRecord, Relationship
from civil_copilot.stores.base import GraphWriteStats, WriteStats, model_fingerprint

SAFE_RELATION = re.compile(r"^[A-Z][A-Z0-9_]*$")


class Neo4jGraphStore:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
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
                    "MATCH (n:ProjectRecord {project_id: $project_id}) RETURN count(n) AS count",
                    project_id=project_id,
                ).single()
            else:
                result = session.run("MATCH (n:ProjectRecord) RETURN count(n) AS count").single()
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
