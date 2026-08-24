import os
from uuid import uuid4

import psycopg
import pytest

from civil_copilot.config import Settings
from civil_copilot.memory.index import PostgresPreferenceIdIndex

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1", reason="local Docker services required"
)
def test_preference_memory_id_survives_a_new_index_instance_and_updates_by_business_key():
    settings = Settings()
    database_url = str(settings.database_url)
    suffix = uuid4().hex
    user_id = f"memory-test-user-{suffix}"
    project_id = f"memory-test-project-{suffix}"
    preference_type = "answer_style"

    first_process = PostgresPreferenceIdIndex(database_url)
    first_process.put(user_id, project_id, preference_type, "mem0-first")

    restarted_process = PostgresPreferenceIdIndex(database_url)
    assert restarted_process.get(user_id, project_id, preference_type) == "mem0-first"

    restarted_process.put(user_id, project_id, preference_type, "mem0-updated")
    assert first_process.get(user_id, project_id, preference_type) == "mem0-updated"

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM preference_memory_index
            WHERE user_id = %s AND project_id = %s AND preference_type = %s
            """,
            (user_id, project_id, preference_type),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            """
            DELETE FROM preference_memory_index
            WHERE user_id = %s AND project_id = %s AND preference_type = %s
            """,
            (user_id, project_id, preference_type),
        )
