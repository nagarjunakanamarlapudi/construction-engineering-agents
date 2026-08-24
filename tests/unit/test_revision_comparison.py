import pytest

from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.revision.service import compare_revision_records


def test_revision_comparison_returns_a_plain_language_field_and_content_diff():
    corpus = generate_demo_project(seed=800)
    drawings = [
        record
        for record in corpus.records
        if record.record_type == "drawing" and record.metadata.get("document_number") == "S-204"
    ]

    comparison = compare_revision_records(
        drawings,
        document_id="S-204",
        from_revision="3",
        to_revision="5",
    )

    assert comparison.from_record_id == "DRAW-S-204-R3"
    assert comparison.to_record_id == "DRAW-S-204-R5"
    assert comparison.status_change == {"from": "superseded", "to": "current"}
    assert comparison.content_similarity < 1.0
    assert "incorporating" in comparison.added_terms
    assert "superseded" in comparison.removed_terms
    assert "S-204 changed from revision 3 to revision 5" in comparison.summary


def test_revision_comparison_requires_both_named_revisions():
    corpus = generate_demo_project(seed=800)

    with pytest.raises(ValueError, match="both requested revisions"):
        compare_revision_records(
            corpus.records,
            document_id="S-204",
            from_revision="3",
            to_revision="99",
        )
