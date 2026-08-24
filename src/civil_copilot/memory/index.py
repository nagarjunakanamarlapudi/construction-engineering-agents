"""Durable mapping from an application preference key to a Mem0 memory ID."""

from __future__ import annotations

import psycopg

INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS preference_memory_index (
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    preference_type TEXT NOT NULL,
    mem0_memory_id TEXT NOT NULL UNIQUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, project_id, preference_type)
)
"""


class PostgresPreferenceIdIndex:
    """Persist Mem0's generated ID under the application's three-part key."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.initialize()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self.database_url,
            connect_timeout=1,
            options="-c statement_timeout=1000",
        )

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(INDEX_SCHEMA)

    def get(self, user_id: str, project_id: str, preference_type: str) -> str | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mem0_memory_id
                FROM preference_memory_index
                WHERE user_id = %s AND project_id = %s AND preference_type = %s
                """,
                (user_id, project_id, preference_type),
            )
            row = cursor.fetchone()
        return str(row[0]) if row else None

    def put(
        self,
        user_id: str,
        project_id: str,
        preference_type: str,
        memory_id: str,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO preference_memory_index (
                    user_id, project_id, preference_type, mem0_memory_id
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, project_id, preference_type) DO UPDATE SET
                    mem0_memory_id = EXCLUDED.mem0_memory_id,
                    updated_at = NOW()
                """,
                (user_id, project_id, preference_type, memory_id),
            )
