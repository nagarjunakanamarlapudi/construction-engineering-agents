import json
from pathlib import Path

import nbformat
from langchain_core.tools import BaseTool
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "06_educational_toy_end_to_end.ipynb"


def _source(notebook: nbformat.NotebookNode) -> str:
    return "\n".join(cell.source for cell in notebook.cells)


def _execute_code_namespace() -> dict[str, object]:
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    code = "\n\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
    code = code.replace("from __future__ import annotations\n", "")
    namespace: dict[str, object] = {"__name__": "toy_notebook_behavior_test"}
    exec(compile(code, str(NOTEBOOK), "exec"), namespace)  # noqa: S102 - teaching notebook contract
    return namespace


def test_educational_notebook_is_a_visible_self_contained_toy():
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    source = _source(notebook)

    assert notebook.metadata["educational_not_production"] is True
    assert source.count("EDUCATIONAL TOY — NOT PRODUCTION") >= 2
    assert "civil_copilot" not in source
    assert "%pip" not in source
    assert "pip install" not in source

    image_paths = (
        "../docs/images/civil-copilot-architecture-overview.png",
        "../docs/images/data-ingestion-architecture.png",
        "../docs/images/data-retrieval-architecture.png",
        "../docs/images/tools-architecture.png",
        "../docs/images/agent-orchestration-architecture.png",
    )
    for image_path in image_paths:
        assert image_path in source
        assert (NOTEBOOK.parent / image_path).resolve().is_file()

    required_lessons = (
        "offline/index-time",
        "exact",
        "sparse",
        "dense",
        "reciprocal rank fusion",
        "rerank",
        "Fast RAG",
        "Graph RAG",
        "ToolInput",
        "Document Specialist",
        "Schedule Specialist",
        "Risk Specialist",
        "Plan → Act → Observe → Decide",
        "allowlisted",
        "citation",
        "abstain",
        "evaluation",
    )
    for lesson in required_lessons:
        assert lesson.lower() in source.lower(), lesson

    forbidden_runtime_dependencies = (
        "requests.",
        "httpx.",
        "openai",
        "mem0",
        "docker",
        "load_dotenv",
        "api_key",
    )
    for dependency in forbidden_runtime_dependencies:
        assert dependency.lower() not in source.lower(), dependency

    assert "from langchain_core.tools import BaseTool, tool" in source
    assert "from langchain.agents import create_agent" in source
    assert source.count("@tool\n") == 5
    assert "TOOL_REGISTRY" in source
    assert ".invoke(request.arguments)" in source
    assert "TOY_AGENT = create_agent(" in source
    assert "TOY_AGENT.invoke(" in source
    assert 'agent_result["messages"]' in source
    assert "def render_agent_trace(" in source
    assert "display(HTML(" in source
    assert "def bounded_react(" not in source


def test_native_agent_trace_contains_tool_calls_observations_and_final_answer():
    namespace = _execute_code_namespace()
    messages = namespace["agent_result"]["messages"]
    trace_rows = namespace["agent_trace_rows"]

    assert messages
    assert any(getattr(message, "tool_calls", None) for message in messages)
    assert any(getattr(message, "type", "") == "tool" for message in messages)
    assert trace_rows[0]["kind"] == "question"
    assert {row["kind"] for row in trace_rows} >= {
        "question",
        "tool_call",
        "tool_observation",
        "final_answer",
    }
    assert trace_rows[-1]["kind"] == "final_answer"
    assert trace_rows[-1]["content"]


def test_educational_notebook_executes_offline_and_verifies_both_examples():
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    executed = NotebookClient(
        notebook,
        timeout=120,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()

    verification_cell = next(
        cell for cell in executed.cells if "toy-verification" in cell.metadata.get("tags", [])
    )
    stream_output = next(
        output.text for output in verification_cell.outputs if output.output_type == "stream"
    )
    verification = json.loads(stream_output)

    assert verification == {
        "abstention": True,
        "agentic_rag": True,
        "all_passed": True,
        "fast_rag": True,
        "graph_rag": True,
        "idempotent_indexing": True,
        "memory": True,
        "observation_branches": True,
        "three_route_examples": True,
    }

    route_cell = next(
        cell for cell in executed.cells if "toy-route-eval" in cell.metadata.get("tags", [])
    )
    route_output = next(
        output.text for output in route_cell.outputs if output.output_type == "stream"
    )
    route_line = next(
        line for line in route_output.splitlines() if line.startswith("ROUTE_EVAL_MATRIX ")
    )
    route_matrix = json.loads(route_line.removeprefix("ROUTE_EVAL_MATRIX "))
    assert set(route_matrix) == {"rag", "graph_rag", "agentic_rag"}
    assert len({item["question"] for item in route_matrix.values()}) == 3
    for expected_route, item in route_matrix.items():
        assert item["route"] == expected_route
        assert item["grounded"] is True
        assert item["citation_ids"]
        assert item["evaluation_passed"] is True


def test_five_toy_tools_are_real_langchain_tools_invoked_through_the_registry():
    namespace = _execute_code_namespace()
    registry = namespace["TOOL_REGISTRY"]

    assert set(registry) == {
        "search_documents",
        "compare_revisions",
        "query_graph",
        "analyze_schedule",
        "rank_risks",
    }
    assert all(isinstance(item, BaseTool) for item in registry.values())

    search_payload = registry["search_documents"].invoke({"question": "What did RFI-087 decide?"})
    assert search_payload["success"] is True
    assert "RFI-087" in search_payload["evidence_ids"]

    observation = namespace["call_tool"](
        namespace["ToolInput"](
            tool_name="analyze_schedule",
            arguments={"activity_id": "ACT-STEEL-009"},
        ),
        "Schedule Specialist",
    )
    assert observation.success is True
    assert observation.specialist == "Schedule Specialist"
    assert observation.data["activity_id"] == "ACT-STEEL-009"


def test_native_agent_uses_returned_observations_for_later_tool_arguments():
    namespace = _execute_code_namespace()
    rows = namespace["agent_trace_rows"]
    calls = {
        row["tool_name"]: row["arguments"]
        for row in rows
        if row["kind"] == "tool_call"
    }

    assert calls["search_documents"]["question"].startswith("Why was ACT-STEEL-009")
    assert calls["analyze_schedule"] == {"activity_id": "ACT-STEEL-009"}
    assert calls["compare_revisions"] == {"document_number": "S-204"}
    assert calls["query_graph"] == {"start_id": "RFI-087"}
    assert {"ACT-STEEL-009", "RFI-087"} <= set(calls["rank_risks"]["evidence_ids"])


def test_native_agent_final_answer_is_built_from_tool_observations():
    namespace = _execute_code_namespace()
    answer = namespace["agent_answer"]

    assert "7 days" in answer.answer
    assert "S-204 revision 5" in answer.answer
    assert "RISK-DELAY-001" in answer.answer
    assert "high" in answer.answer and "mitigated" in answer.answer
    assert {"ACT-STEEL-009", "RFI-087", "DRAW-S-204-R5"} <= {
        citation.record_id for citation in answer.citations
    }


def test_graph_rag_renders_each_relationship_once():
    namespace = _execute_code_namespace()
    answer = namespace["graph_rag"]("RFI-087")

    assert answer.answer.count("RFI-087 AFFECTS ACT-STEEL-009") == 1
