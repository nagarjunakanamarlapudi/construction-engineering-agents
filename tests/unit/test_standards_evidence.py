from civil_copilot.agents.tools import ProjectTools
from civil_copilot.data.loaders import load_corpus
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.standards.service import StandardsEvidenceService


def _service(*, include_public_scope: bool = True) -> StandardsEvidenceService:
    corpus = load_corpus()
    tools = ProjectTools(
        corpus.records,
        retriever=object(),  # This deterministic service reads records, not semantic search.
        graph=ProjectGraphService(corpus.records, corpus.relationships),
    )
    return StandardsEvidenceService(
        tools,
        project_id="BLR-STEEL-DEMO",
        access_scopes=("project:blr-steel-demo",) + (("public",) if include_public_scope else ()),
    )


def test_is_800_report_compares_seven_preview_topics_without_claiming_conformance():
    report = _service().assess("IS 800:2007")

    assert report.standard_record_id == "CODE-IS-800"
    assert report.official_record_id == "PUBLIC-BIS-bis-800"
    assert [row.topic_id for row in report.rows] == [
        "steel-construction-scope",
        "material-references",
        "welding-records",
        "fabrication-and-erection",
        "inspection-and-acceptance",
        "load-references",
        "seismic-references",
    ]
    assert {row.status for row in report.rows} == {
        "Evidenced",
        "Not evidenced",
        "Needs review",
    }
    assert all(row.project_evidence for row in report.rows)
    assert all(row.official_source.record_id == "PUBLIC-BIS-bis-800" for row in report.rows)
    assert all(row.official_source.chunk_id.startswith("bis-800-chunk-") for row in report.rows)
    assert all(row.official_source.data_origin == "public_official" for row in report.rows)
    assert all(
        citation.data_origin == "synthetic_academic_demo"
        for row in report.rows
        for citation in row.project_evidence
    )
    serialized = report.model_dump_json()
    assert '"status":"Compliant"' not in serialized
    assert '"status":"Non-compliant"' not in serialized
    assert "Missing evidence is not proof that a practice was not followed" in report.limitation
    assert "public preview" in report.limitation.lower()


def test_is_800_report_requires_both_project_and_public_access():
    service = _service(include_public_scope=False)

    try:
        service.assess("IS 800:2007")
    except PermissionError as error:
        assert "public preview" in str(error).lower()
    else:
        raise AssertionError("the official preview must not bypass public access control")


def test_unknown_or_unimplemented_standard_is_rejected_without_guessing():
    service = _service()

    try:
        service.assess("IS 875:1987")
    except ValueError as error:
        assert "supported" in str(error).lower()
        assert "IS 800:2007" in str(error)
    else:
        raise AssertionError("an unsupported checklist must not be inferred")
