import pytest

from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.graph.service import ProjectGraphService


def test_graph_paths_are_depth_limited_and_keep_relationship_provenance():
    corpus = generate_demo_project(seed=800)
    graph = ProjectGraphService(corpus.records, corpus.relationships)

    paths = graph.find_paths("RFI-087", max_depth=2, direction="outgoing")

    assert paths
    assert all(path.depth <= 2 for path in paths)
    assert any(path.end_id == "ACT-STEEL-009" for path in paths)
    assert any(path.end_id == "DRAW-S-204-R5" for path in paths)
    assert all(edge.provenance for path in paths for edge in path.edges)


def test_graph_rejects_unbounded_or_unknown_path_requests():
    corpus = generate_demo_project(seed=800)
    graph = ProjectGraphService(corpus.records, corpus.relationships)

    with pytest.raises(ValueError, match="between 1 and 5"):
        graph.find_paths("RFI-087", max_depth=20)
    with pytest.raises(KeyError, match="UNKNOWN"):
        graph.find_paths("UNKNOWN", max_depth=2)


def test_portable_graph_can_follow_exact_project_standard_link_to_public_preview():
    corpus = load_corpus()
    graph = ProjectGraphService(corpus.records, corpus.relationships)

    paths = graph.find_paths(
        "CODE-IS-800",
        max_depth=1,
        direction="outgoing",
        relationship_types={"REFERENCES"},
    )

    public_path = next(path for path in paths if path.end_id == "PUBLIC-BIS-bis-800")
    assert public_path.nodes[0].data_origin == "synthetic_academic_demo"
    assert public_path.nodes[1].data_origin == "public_official"
    assert public_path.edges[0].method == "explicit_standard_designation_mapping"
