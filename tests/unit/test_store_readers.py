from datetime import date

from civil_copilot.data.models import ProjectRecord
from civil_copilot.stores.base import InMemoryRecordStore
from civil_copilot.stores.postgres import PostgresRecordStore


def _record(
    record_id: str,
    *,
    project_id: str = "PROJECT-1",
    effective_date: date = date(2026, 1, 1),
    access_scopes: list[str] | None = None,
) -> ProjectRecord:
    return ProjectRecord(
        record_id=record_id,
        project_id=project_id,
        record_type="rfi",
        title=record_id,
        content=f"Evidence for {record_id}",
        status="current",
        revision="1",
        effective_date=effective_date,
        data_origin="synthetic_academic_demo",
        source_path=f"data/test#{record_id}",
        access_scopes=access_scopes or ["role:engineer"],
    )


def test_record_reader_filters_project_acl_metadata_and_as_of_date_before_returning_rows():
    store = InMemoryRecordStore()
    store.upsert_records(
        [
            _record("RFI-VISIBLE", effective_date=date(2026, 2, 1)),
            _record("RFI-FUTURE", effective_date=date(2026, 8, 1)),
            _record("RFI-RESTRICTED", access_scopes=["role:commercial"]),
            _record("RFI-OTHER-PROJECT", project_id="PROJECT-2"),
        ]
    )

    query_records = getattr(store, "query_records", lambda **_kwargs: [])
    records = query_records(
        project_id="PROJECT-1",
        access_scopes=["role:engineer"],
        as_of_date=date(2026, 6, 1),
        metadata_filters={},
        limit=20,
    )

    assert [record.record_id for record in records] == ["RFI-VISIBLE"]


class _Cursor:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.query = ""
        self.parameters: dict[str, object] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query: str, parameters: dict[str, object]) -> None:
        self.query = query
        self.parameters = parameters

    def fetchall(self) -> list[tuple[dict[str, object]]]:
        return [(self.payload,)]


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


def test_postgres_reader_pushes_acl_metadata_and_as_of_filters_into_the_database(monkeypatch):
    visible = _record("RFI-VISIBLE", effective_date=date(2026, 2, 1))
    cursor = _Cursor(visible.model_dump(mode="json"))
    store = PostgresRecordStore.__new__(PostgresRecordStore)
    monkeypatch.setattr(store, "_connect", lambda: _Connection(cursor))

    query_records = getattr(store, "query_records", lambda **_kwargs: [])
    records = query_records(
        project_id="PROJECT-1",
        access_scopes=["role:engineer"],
        record_types=["rfi"],
        statuses=["current"],
        as_of_date=date(2026, 6, 1),
        metadata_filters={"discipline": "structural"},
        limit=20,
    )

    assert [record.record_id for record in records] == ["RFI-VISIBLE"]
    assert "access_scopes ?| %(access_scopes)s" in cursor.query
    assert "effective_date <= %(as_of_date)s" in cursor.query
    assert "metadata @> %(metadata_filters)s::jsonb" in cursor.query
    assert cursor.parameters["access_scopes"] == ["role:engineer"]
