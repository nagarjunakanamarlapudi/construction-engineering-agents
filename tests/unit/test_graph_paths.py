import pytest

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
