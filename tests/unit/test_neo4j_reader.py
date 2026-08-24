from datetime import date

from civil_copilot.stores.neo4j import Neo4jGraphStore


class _Session:
    def __init__(self) -> None:
        self.query = ""
        self.query_timeout: float | None = None
        self.parameters: dict[str, object] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def run(self, query: str, **parameters):
        self.query = getattr(query, "text", query)
        self.query_timeout = getattr(query, "timeout", None)
        self.parameters = parameters
        return [
            {
                "nodes": [
                    {
                        "record_id": "RFI-087",
                        "record_type": "rfi",
                        "title": "RFI 087",
                        "status": "closed",
                        "data_origin": "synthetic_academic_demo",
                        "source_path": "data/test#RFI-087",
                    },
                    {
                        "record_id": "ACT-009",
                        "record_type": "schedule_activity",
                        "title": "Activity 009",
                        "status": "planned",
                        "data_origin": "synthetic_academic_demo",
                        "source_path": "data/test#ACT-009",
                    },
                ],
                "edges": [
                    {
                        "relationship_id": "REL-1",
                        "source_id": "RFI-087",
                        "target_id": "ACT-009",
                        "relationship_type": "AFFECTS",
                        "provenance": "approved register",
                        "method": "structured_export",
                        "confidence": 1.0,
                        "valid_from": date(2026, 2, 1),
                    }
                ],
            }
        ]


class _Driver:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def session(self) -> _Session:
        return self._session


class _IncomingOnlySession(_Session):
    def run(self, query: str, **parameters):
        self.query = getattr(query, "text", query)
        self.query_timeout = getattr(query, "timeout", None)
        self.parameters = parameters
        return [
            {
                "nodes": [
                    {
                        "record_id": "RFI-087",
                        "record_type": "rfi",
                        "title": "RFI 087",
                        "status": "closed",
                        "data_origin": "synthetic_academic_demo",
                        "source_path": "data/test#RFI-087",
                    },
                    {
                        "record_id": "MIN-STEEL-07",
                        "record_type": "meeting_minute",
                        "title": "Steel coordination meeting 07",
                        "status": "issued",
                        "data_origin": "synthetic_academic_demo",
                        "source_path": "data/test#MIN-STEEL-07",
                    },
                ],
                "edges": [
                    {
                        "relationship_id": "REL-INCOMING",
                        "source_id": "MIN-STEEL-07",
                        "target_id": "RFI-087",
                        "relationship_type": "DISCUSSES",
                        "provenance": "approved meeting minute",
                        "method": "structured_export",
                        "confidence": 1.0,
                        "valid_from": date(2026, 5, 9),
                    }
                ],
            }
        ]


class _InitializationResult:
    def consume(self):
        return None


class _InitializationSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def run(self, *_args, **_kwargs):
        return _InitializationResult()


class _InitializationDriver:
    def verify_connectivity(self):
        return None

    def session(self):
        return _InitializationSession()


def test_neo4j_reader_enforces_acl_time_relation_and_depth_inside_the_live_query():
    session = _Session()
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    store.driver = _Driver(session)

    find_paths = getattr(store, "find_paths", lambda *_args, **_kwargs: [])
    paths = find_paths(
        "RFI-087",
        project_id="PROJECT-1",
        access_scopes=["role:engineer"],
        max_depth=2,
        direction="outgoing",
        relationship_types={"AFFECTS"},
        as_of_date=date(2026, 6, 1),
        max_paths=10,
    )

    assert paths[0].end_id == "ACT-009"
    assert paths[0].edges[0].method == "structured_export"
    assert paths[0].edges[0].valid_from == date(2026, 2, 1)
    assert "-[rels*1..2]->" in session.query
    assert "any(scope IN node.access_scopes WHERE scope IN $access_scopes)" in session.query
    assert session.parameters["relationship_types"] == ["AFFECTS"]
    assert session.parameters["as_of_date"] == "2026-06-01"
    assert session.query_timeout == 2.0


def test_neo4j_reader_allows_public_reference_nodes_only_with_public_scope():
    session = _Session()
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    store.driver = _Driver(session)

    store.find_paths(
        "CODE-IS-800",
        project_id="BLR-STEEL-DEMO",
        access_scopes=["project:blr-steel-demo", "public"],
        max_depth=1,
        direction="outgoing",
        relationship_types={"REFERENCES"},
    )

    assert session.parameters["allowed_project_ids"] == [
        "BLR-STEEL-DEMO",
        "PUBLIC-REFERENCE",
    ]
    assert "node.project_id IN $allowed_project_ids" in session.query


def test_neo4j_reader_both_direction_uses_undirected_pattern_for_incoming_only_path():
    session = _IncomingOnlySession()
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    store.driver = _Driver(session)

    paths = store.find_paths(
        "RFI-087",
        project_id="PROJECT-1",
        access_scopes=["role:engineer"],
        max_depth=2,
        direction="both",
        relationship_types={"DISCUSSES"},
        max_paths=10,
    )

    assert "MATCH path=(start)-[rels*1..2]-(end)" in session.query
    assert "MATCH path=(start)-[rels*1..2]->(end)" not in session.query
    assert paths[0].end_id == "MIN-STEEL-07"
    assert paths[0].edges[0].source_id == "MIN-STEEL-07"
    assert paths[0].edges[0].target_id == "RFI-087"


def test_neo4j_driver_bounds_pool_acquisition_and_disables_transaction_retries(monkeypatch):
    captured: dict[str, object] = {}

    def build_driver(uri: str, **configuration):
        captured["uri"] = uri
        captured.update(configuration)
        return _InitializationDriver()

    monkeypatch.setattr("civil_copilot.stores.neo4j.GraphDatabase.driver", build_driver)

    Neo4jGraphStore("bolt://neo4j:7687", "neo4j", "test-password")

    assert captured["connection_timeout"] == 1.0
    assert captured["connection_acquisition_timeout"] == 1.5
    assert captured["max_transaction_retry_time"] == 0.0
