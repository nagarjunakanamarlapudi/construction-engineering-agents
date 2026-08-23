import hashlib
import json

from civil_copilot.data.synthetic import generate_demo_project, write_demo_project


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_demo_project_is_deterministic_connected_and_traceable(tmp_path):
    first = generate_demo_project(seed=800)
    second = generate_demo_project(seed=800)

    assert _digest(first.model_dump(mode="json")) == _digest(second.model_dump(mode="json"))
    assert len(first.records) >= 150
    assert len(first.relationships) >= 200
    assert len(first.chunks) >= len(first.records)

    record_ids = {record.record_id for record in first.records}
    assert len(record_ids) == len(first.records)
    assert all(
        link.source_id in record_ids and link.target_id in record_ids
        for link in first.relationships
    )
    assert all(record.data_origin == "synthetic_academic_demo" for record in first.records)
    assert all(record.source_path and record.access_scopes for record in first.records)
    assert all(record.revision and record.effective_date for record in first.records)
    assert all(
        link.provenance and link.method == "synthetic_ground_truth" for link in first.relationships
    )

    output = tmp_path / "demo"
    manifest = write_demo_project(first, output)
    assert manifest["record_count"] == len(first.records)
    assert manifest["dangling_relationship_count"] == 0
    assert (output / "records.jsonl").exists()
    assert (output / "chunks.jsonl").exists()
    assert (output / "relationships.jsonl").exists()


def test_demo_project_covers_required_civil_engineering_records_and_paths():
    corpus = generate_demo_project(seed=800)
    record_types = {record.record_type for record in corpus.records}

    assert {
        "code_register",
        "code_reference",
        "specification",
        "calculation",
        "drawing",
        "rfi",
        "schedule_activity",
        "purchase_order",
        "material_certificate",
        "piece",
        "weld",
        "inspection",
        "ncr",
        "meeting_minute",
        "handover",
    } <= record_types

    relation_types = {link.relationship_type for link in corpus.relationships}
    assert {
        "ADOPTS",
        "IMPLEMENTS",
        "SUPPORTS",
        "REVISES",
        "REFERENCES",
        "AFFECTS",
        "DEPENDS_ON",
        "FULFILLED_BY",
        "USED_IN",
        "JOINS",
        "TESTS",
        "RAISES",
        "CORRECTED_BY",
        "HANDOVER_EVIDENCE_FOR",
    } <= relation_types


def test_every_ncr_is_raised_by_a_rejected_inspection():
    corpus = generate_demo_project(seed=800)
    records = {record.record_id: record for record in corpus.records}
    raises = [link for link in corpus.relationships if link.relationship_type == "RAISES"]

    assert raises
    for link in raises:
        assert records[link.source_id].record_type == "inspection"
        assert records[link.source_id].status == "rejected"
        if records[link.target_id].status == "open":
            weld_id = link.source_id.replace("INSP-", "")
            assert records[weld_id].status == "repair_required"
