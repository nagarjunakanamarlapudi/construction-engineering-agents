from importlib import import_module

import pytest


def _presenters():
    try:
        return import_module("civil_copilot.ui.presenters")
    except ModuleNotFoundError:
        pytest.fail("The readable UI presentation adapter has not been implemented yet.")


def test_scenario_options_reject_json_error_objects_instead_of_iterating_their_keys():
    normalizer = getattr(_presenters(), "normalize_scenarios", None)

    assert normalizer is not None, "The scenario API response needs a UI boundary normalizer."
    assert normalizer({"detail": "Not Found"}) == []


def test_scenario_options_keep_only_renderable_scenario_objects():
    scenario = {
        "scenario_id": "S-01",
        "title": "Trace an RFI decision",
        "question": "What did RFI-087 decide?",
        "expected_route": "rag",
        "expected_evidence_ids": ["RFI-087"],
        "expected_tools": ["search_project_records"],
        "explanation": "A direct evidence lookup.",
    }

    normalized = _presenters().normalize_scenarios(
        [scenario, "detail", None, {"scenario_id": "S-incomplete"}]
    )

    assert normalized == [scenario]


def test_answer_presentation_removes_index_metadata_from_reader_facing_text():
    response = {
        "question": "Why was activity ACT-STEEL-009 blocked?",
        "route": "agentic_rag",
        "answer": (
            "SYNTHETIC — ACADEMIC DEMO: Steel work activity 009. "
            "Record ACT-STEEL-009; type schedule_activity; status in_progress; "
            "revision baseline-2; effective 2026-02-18. SYNTHETIC — ACADEMIC DEMO. "
            "Fabricate, deliver, or erect structural steel for level 2, zone 3. "
            "Planned duration: 7 days. "
            "[ACT-STEEL-009](http://127.0.0.1:8011/api/records/ACT-STEEL-009)\n\n"
            "SYNTHETIC — ACADEMIC DEMO: Structural clarification 087. "
            "Record RFI-087; type rfi; status closed; revision response-1; "
            "effective 2026-03-12. SYNTHETIC — ACADEMIC DEMO. "
            "The approved response required plate PL-17B and was incorporated in S-204 Rev 5. "
            "[RFI-087](http://127.0.0.1:8011/api/records/RFI-087)"
        ),
        "citations": [{"record_id": "ACT-STEEL-009"}, {"record_id": "RFI-087"}],
        "graph_paths": [],
        "grounded": True,
        "abstained": False,
    }

    presentation = _presenters().build_answer_presentation(response)

    assert presentation.finding == (
        "ACT-STEEL-009 was blocked pending the clarification described in the evidence."
    )
    assert presentation.explanation == (
        "The approved response required plate PL-17B and was incorporated in S-204 Rev 5."
    )
    reader_text = " ".join(
        [presentation.finding, presentation.explanation, *presentation.connections]
    )
    assert "type schedule_activity" not in reader_text
    assert "revision baseline-2" not in reader_text
    assert "SYNTHETIC — ACADEMIC DEMO" not in reader_text


def test_answer_presentation_translates_graph_edges_into_plain_connections():
    response = {
        "question": "What is downstream of RFI-087?",
        "route": "graph_rag",
        "answer": "The approved response changed drawing S-204 Rev 5.",
        "citations": [{"record_id": "RFI-087"}],
        "graph_paths": [
            {
                "nodes": [
                    {"record_id": "RFI-087", "record_type": "rfi"},
                    {"record_id": "DRAW-S-204-R5", "record_type": "drawing"},
                    {"record_id": "ACT-STEEL-009", "record_type": "schedule_activity"},
                ],
                "edges": [
                    {
                        "source_id": "RFI-087",
                        "target_id": "DRAW-S-204-R5",
                        "relationship_type": "CHANGES_OR_CLARIFIES",
                    },
                    {
                        "source_id": "RFI-087",
                        "target_id": "ACT-STEEL-009",
                        "relationship_type": "AFFECTS",
                    },
                ],
            }
        ],
        "grounded": True,
        "abstained": False,
    }

    presentation = _presenters().build_answer_presentation(response)

    assert presentation.finding == (
        "RFI-087 directly affects ACT-STEEL-009 and changes or clarifies DRAW-S-204-R5."
    )
    assert presentation.explanation == "The approved response changed drawing S-204 Rev 5."
    assert presentation.connections == (
        "RFI-087 changes or clarifies DRAW-S-204-R5.",
        "RFI-087 affects ACT-STEEL-009.",
    )
    assert presentation.source_count == 1


def test_answer_presentation_limits_connections_to_the_named_project_record():
    response = {
        "question": "What is the impact of RFI-087?",
        "route": "graph_rag",
        "answer": "The RFI changed the approved connection detail.",
        "citations": [],
        "graph_paths": [
            {
                "edges": [
                    {
                        "source_id": "RFI-087",
                        "target_id": "ACT-STEEL-009",
                        "relationship_type": "AFFECTS",
                    },
                    {
                        "source_id": "RFI-085",
                        "target_id": "ACT-STEEL-009",
                        "relationship_type": "AFFECTS",
                    },
                ]
            }
        ],
        "grounded": True,
        "abstained": False,
    }

    presentation = _presenters().build_answer_presentation(response)

    assert presentation.connections == ("RFI-087 affects ACT-STEEL-009.",)


def test_route_label_preserves_rag_acronym():
    assert _presenters().route_label("rag") == "RAG"
    assert _presenters().route_label("graph_rag") == "Graph RAG"
    assert _presenters().route_label("agentic_rag") == "Agentic RAG"


def test_humanize_token_replaces_storage_formatting_for_readers():
    assert _presenters().humanize_token("repair_and_reinspect") == "Repair and reinspect"
    assert _presenters().humanize_token("in_progress") == "In progress"


def test_answer_presentation_keeps_safe_abstention_as_the_main_finding():
    response = {
        "question": "What caused the delay?",
        "route": "rag",
        "answer": (
            "I do not have enough evidence in the permitted project sources to answer "
            "this question."
        ),
        "citations": [],
        "graph_paths": [],
        "grounded": True,
        "abstained": True,
    }

    presentation = _presenters().build_answer_presentation(response)

    assert presentation.finding == response["answer"]
    assert presentation.explanation == ""
    assert presentation.connections == ()
    assert presentation.source_count == 0


def test_revision_preview_hides_ingestion_headers_but_preserves_control_fields():
    revision = {
        "record_id": "DRAW-S-204-R5",
        "revision": "5",
        "status": "current",
        "effective_date": "2026-02-28",
        "content": (
            "SYNTHETIC — ACADEMIC DEMO: S-204 framing plan revision 5. "
            "Record DRAW-S-204-R5; type drawing; status current; revision 5; "
            "effective 2026-02-28. SYNTHETIC — ACADEMIC DEMO. "
            "Current issued-for-construction plan for grid 4 with approved connection details."
        ),
    }

    preview = _presenters().build_revision_preview(revision)

    assert preview.record_id == "DRAW-S-204-R5"
    assert preview.revision == "5"
    assert preview.status == "Current"
    assert preview.summary == (
        "Current issued-for-construction plan for grid 4 with approved connection details."
    )


def test_standard_matrix_rows_keep_status_reason_and_both_source_classes_readable():
    report = {
        "rows": [
            {
                "topic_id": "welding-records",
                "topic": "Welding work records a procedure and inspection result.",
                "status": "Evidenced",
                "reason": "A WPS, welder, and inspection are recorded.",
                "project_evidence": [
                    {"record_id": "WELD-001"},
                    {"record_id": "INSP-WELD-001"},
                ],
                "official_source": {
                    "record_id": "PUBLIC-BIS-bis-800",
                    "chunk_id": "bis-800-chunk-0002",
                },
            }
        ]
    }

    rows = _presenters().build_standard_matrix_rows(report)

    assert rows[0].topic == "Welding work records a procedure and inspection result."
    assert rows[0].status == "Evidenced"
    assert rows[0].reason == "A WPS, welder, and inspection are recorded."
    assert rows[0].project_sources == ("WELD-001", "INSP-WELD-001")
    assert rows[0].official_source == "PUBLIC-BIS-bis-800 · bis-800-chunk-0002"
