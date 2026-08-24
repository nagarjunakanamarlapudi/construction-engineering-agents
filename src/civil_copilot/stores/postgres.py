"""PostgreSQL adapter for authoritative structured project records."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import psycopg

from civil_copilot.data.models import ProjectRecord
from civil_copilot.stores.base import WriteStats, model_fingerprint

SCHEMA = Path(__file__).resolve().parents[3] / "sql" / "schema.sql"
STORE_TIMEOUT_SECONDS = 1


class PostgresRecordStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.initialize()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self.database_url,
            connect_timeout=STORE_TIMEOUT_SECONDS,
            options=f"-c statement_timeout={STORE_TIMEOUT_SECONDS * 1000}",
        )

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA.read_text(encoding="utf-8"))

    def upsert_records(self, records: list[ProjectRecord]) -> WriteStats:
        if not records:
            return WriteStats()
        created = updated = unchanged = 0
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT record_id, content_hash FROM project_records WHERE record_id = ANY(%s)",
                ([record.record_id for record in records],),
            )
            existing = dict(cursor.fetchall())
            for record in records:
                fingerprint = model_fingerprint(record)
                if record.record_id not in existing:
                    created += 1
                elif existing[record.record_id] == fingerprint:
                    unchanged += 1
                    continue
                else:
                    updated += 1
                payload = record.model_dump(mode="json")
                cursor.execute(
                    """
                    INSERT INTO project_records (
                        record_id, project_id, record_type, title, content, status, revision,
                        effective_date, data_origin, source_path, source_url, access_scopes,
                        metadata, payload, content_hash
                    ) VALUES (
                        %(record_id)s, %(project_id)s, %(record_type)s, %(title)s, %(content)s,
                        %(status)s, %(revision)s, %(effective_date)s, %(data_origin)s,
                        %(source_path)s, %(source_url)s, %(access_scopes)s, %(metadata)s,
                        %(payload)s, %(content_hash)s
                    )
                    ON CONFLICT (record_id) DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        record_type = EXCLUDED.record_type,
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        status = EXCLUDED.status,
                        revision = EXCLUDED.revision,
                        effective_date = EXCLUDED.effective_date,
                        data_origin = EXCLUDED.data_origin,
                        source_path = EXCLUDED.source_path,
                        source_url = EXCLUDED.source_url,
                        access_scopes = EXCLUDED.access_scopes,
                        metadata = EXCLUDED.metadata,
                        payload = EXCLUDED.payload,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = NOW()
                    """,
                    {
                        **payload,
                        "access_scopes": json.dumps(payload["access_scopes"]),
                        "metadata": json.dumps(payload["metadata"]),
                        "payload": json.dumps(payload),
                        "content_hash": fingerprint,
                    },
                )
        return WriteStats(created, updated, unchanged)

    def count(self) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM project_records")
            return int(cursor.fetchone()[0])

    def get(self, record_id: str) -> ProjectRecord | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT payload FROM project_records WHERE record_id = %s", (record_id,))
            row = cursor.fetchone()
        return ProjectRecord.model_validate(row[0]) if row else None

    def list(self, project_id: str | None = None) -> list[ProjectRecord]:
        query = "SELECT payload FROM project_records"
        params: tuple[str, ...] = ()
        if project_id:
            query += " WHERE project_id = %s"
            params = (project_id,)
        query += " ORDER BY record_id"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return [ProjectRecord.model_validate(row[0]) for row in cursor.fetchall()]

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
        """Read authorized records with filters enforced by PostgreSQL."""

        if not access_scopes or limit < 1:
            return []
        clauses = [
            "project_id = %(project_id)s",
            "access_scopes ?| %(access_scopes)s",
        ]
        parameters: dict[str, object] = {
            "project_id": project_id,
            "access_scopes": access_scopes,
            "limit": min(limit, 500),
        }
        if record_ids:
            clauses.append("record_id = ANY(%(record_ids)s)")
            parameters["record_ids"] = record_ids
        if record_types:
            clauses.append("record_type = ANY(%(record_types)s)")
            parameters["record_types"] = record_types
        if statuses:
            clauses.append("status = ANY(%(statuses)s)")
            parameters["statuses"] = statuses
        if as_of_date is not None:
            clauses.append("effective_date <= %(as_of_date)s")
            parameters["as_of_date"] = as_of_date
        if metadata_filters:
            clauses.append("metadata @> %(metadata_filters)s::jsonb")
            parameters["metadata_filters"] = json.dumps(metadata_filters)
        where_clause = " AND ".join(clauses)
        query = (
            f"SELECT payload FROM project_records WHERE {where_clause} "  # noqa: S608  # nosec B608
            "ORDER BY effective_date DESC, record_id LIMIT %(limit)s"
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return [ProjectRecord.model_validate(row[0]) for row in cursor.fetchall()]
