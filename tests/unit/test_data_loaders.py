import json

from civil_copilot.data.loaders import load_corpus, load_gold_scenarios
from civil_copilot.data.synthetic import generate_demo_project, write_demo_project


def test_loader_combines_synthetic_records_with_public_bis_chunks(tmp_path):
    root = tmp_path
    synthetic = root / "data" / "synthetic" / "steel_building_demo"
    public = root / "data" / "public" / "bis" / "academic"
    public.mkdir(parents=True)
    write_demo_project(generate_demo_project(seed=800), synthetic)

    public_chunk = {
        "chunk_id": "bis-800-chunk-0001",
        "source_id": "bis-800",
        "designation": "IS 800 : 2007",
        "title": "General Construction in Steel",
        "text": "Official public preview scope text.",
        "data_origin": "public_official",
        "source_url": "https://example.invalid/bis-800",
        "access_type": "official_public_preview",
        "content_scope": "public_preview_or_metadata_not_full_standard",
    }
    (public / "INDEX.jsonl").write_text(json.dumps(public_chunk) + "\n", encoding="utf-8")

    corpus = load_corpus(root)

    assert any(chunk.chunk_id == "bis-800-chunk-0001" for chunk in corpus.chunks)
    chunk = next(chunk for chunk in corpus.chunks if chunk.chunk_id == "bis-800-chunk-0001")
    assert chunk.data_origin == "public_official"
    assert chunk.metadata["content_scope"] == "public_preview_or_metadata_not_full_standard"
    assert any(record.record_id == "PUBLIC-BIS-bis-800" for record in corpus.records)


def test_loader_adds_only_explicit_exact_project_to_public_standard_links(tmp_path):
    root = tmp_path
    synthetic = root / "data" / "synthetic" / "steel_building_demo"
    public = root / "data" / "public" / "bis" / "academic"
    public.mkdir(parents=True)
    write_demo_project(generate_demo_project(seed=800), synthetic)
    public_chunks = [
        {
            "chunk_id": "bis-800-chunk-0001",
            "source_id": "bis-800",
            "designation": "IS 800 : 2007",
            "title": "General Construction in Steel",
            "text": "Official public preview scope text.",
            "data_origin": "public_official",
            "source_url": "https://example.invalid/bis-800",
            "access_type": "official_public_preview",
            "content_scope": "public_preview_or_metadata_not_full_standard",
        },
        {
            "chunk_id": "bis-875-1-2026-chunk-0001",
            "source_id": "bis-875-1-2026",
            "designation": "IS 875 : Part 1 : 2026",
            "title": "Dead loads",
            "text": "Official public preview scope text.",
            "data_origin": "public_official",
            "source_url": "https://example.invalid/bis-875-1-2026",
            "access_type": "official_public_preview",
            "content_scope": "public_preview_or_metadata_not_full_standard",
        },
    ]
    (public / "INDEX.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in public_chunks), encoding="utf-8"
    )

    corpus = load_corpus(root)

    official_links = [
        link
        for link in corpus.relationships
        if link.method == "explicit_standard_designation_mapping"
    ]
    assert [
        (link.source_id, link.target_id, link.relationship_type) for link in official_links
    ] == [("CODE-IS-800", "PUBLIC-BIS-bis-800", "REFERENCES")]
    assert official_links[0].metadata == {
        "project_source_classification": "synthetic_project_reference",
        "public_source_classification": "public_official_preview",
        "content_scope": "public_preview_or_metadata_not_full_standard",
        "mapping_basis": "exact_designation_and_edition",
    }


def test_gold_scenarios_have_six_routes_and_expected_evidence(tmp_path):
    scenarios_path = tmp_path / "scenarios.json"
    scenarios_path.write_text(
        json.dumps(
            [
                {
                    "scenario_id": f"S-{number}",
                    "question": f"Question {number}",
                    "expected_route": route,
                    "expected_evidence_ids": ["RFI-087"],
                    "expected_tools": ["search_documents"],
                }
                for number, route in enumerate(
                    ["rag", "rag", "graph_rag", "agentic_rag", "graph_rag", "agentic_rag"],
                    start=1,
                )
            ]
        ),
        encoding="utf-8",
    )

    scenarios = load_gold_scenarios(scenarios_path)

    assert len(scenarios) == 6
    assert {scenario.expected_route for scenario in scenarios} == {
        "rag",
        "graph_rag",
        "agentic_rag",
    }
    assert all(scenario.expected_evidence_ids for scenario in scenarios)
