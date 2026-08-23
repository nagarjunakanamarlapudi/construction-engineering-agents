import pytest

from civil_copilot.agents.tools import ProjectTools, ToolRequest
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.graph.service import ProjectGraphService
from civil_copilot.retrieval.hybrid import HybridRetriever


def _tools() -> ProjectTools:
    corpus = generate_demo_project(seed=800)

    def vector_search(_query: str, limit: int) -> list[tuple[str, float]]:
        return [(chunk.chunk_id, 0.5) for chunk in corpus.chunks[:limit]]

    return ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, vector_search),
        ProjectGraphService(corpus.records, corpus.relationships),
    )


def test_tools_validate_inputs_enforce_access_and_return_citable_observations():
    tools = _tools()
    observation = tools.call(
        ToolRequest(
            tool_name="get_records",
            arguments={"record_ids": ["RFI-087", "DRAW-S-204-R5"]},
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
        )
    )

    assert observation.success is True
    assert observation.evidence_ids == ["RFI-087", "DRAW-S-204-R5"]
    assert observation.citations

    quality = tools.call(
        ToolRequest(
            tool_name="query_quality_records",
            arguments={"status": "open"},
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
        )
    )
    assert "status open" in quality.evidence[0].chunk.text.lower()

    with pytest.raises(PermissionError):
        tools.call(
            ToolRequest(
                tool_name="get_records",
                arguments={"record_ids": ["RFI-087"]},
                project_id="BLR-STEEL-DEMO",
                access_scopes=["public"],
            )
        )

    with pytest.raises(ValueError, match="Unknown tool"):
        tools.call(
            ToolRequest(
                tool_name="delete_records",
                arguments={},
                project_id="BLR-STEEL-DEMO",
                access_scopes=["project:blr-steel-demo"],
            )
        )
