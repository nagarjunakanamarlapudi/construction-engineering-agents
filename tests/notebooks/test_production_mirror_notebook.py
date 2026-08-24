import json
import os
import re
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "07_production_mirror_end_to_end.ipynb"


def _read_notebook():
    return nbformat.read(NOTEBOOK, as_version=4)


def _code(notebook) -> str:
    return "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")


def _markdown(notebook) -> str:
    return "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")


def test_production_mirror_notebook_is_a_thin_48_cell_control_surface():
    notebook = _read_notebook()
    assert len(notebook.cells) == 48
    assert notebook.metadata["production_mirror"] is True

    markdown = _markdown(notebook)
    code = _code(notebook)

    required_markers = (
        "PRODUCTION MIRROR",
        "portable",
        "local",
        "live",
        "SYNTHETIC",
        "PUBLIC",
        "Offline indexing",
        "Hybrid retrieval",
        "Fast RAG",
        "Graph RAG",
        "Bounded ReAct",
        "Preference memory",
        "Evaluation",
        "assess_standard_evidence",
        "No silent fallback",
    )
    for marker in required_markers:
        assert marker in markdown

    image_paths = (
        "../docs/images/civil-copilot-architecture-overview.png",
        "../docs/images/data-ingestion-architecture.png",
        "../docs/images/data-retrieval-architecture.png",
        "../docs/images/tools-architecture.png",
        "../docs/images/agent-orchestration-architecture.png",
    )
    for image_path in image_paths:
        assert image_path in markdown
        assert (NOTEBOOK.parent / image_path).resolve().is_file()

    required_production_symbols = (
        "build_application_runtime",
        "build_runtime",
        "RuntimeMode",
        "IngestionService",
        "GroundedAnswerService",
        "DEFAULT_TOOL_REGISTRY",
        "ReactAgentSuite",
        "PreferenceMemory",
        "EvaluationRunner",
        "default_gold_scenarios",
        "inspect.getsource",
    )
    for symbol in required_production_symbols:
        assert symbol in code

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        assert not re.search(r"^\s*(?:async\s+)?def\s+", cell.source, re.MULTILINE)
        assert not re.search(r"^\s*class\s+", cell.source, re.MULTILINE)

    forbidden = (
        "pip install",
        "%pip",
        "docker compose up",
        "services-up",
        "MemoryClient(",
        "OpenAI(",
        "ChatOpenAI(",
    )
    for value in forbidden:
        assert value not in code
    assert not re.search(r"(?:sk-|mem0-|pk-lf-|sk-lf-)[A-Za-z0-9_-]{12,}", code)


def test_production_mirror_notebook_owns_runtime_lifecycle_and_describes_modes_truthfully():
    notebook = _read_notebook()
    markdown = _markdown(notebook)
    lower_markdown = markdown.lower()
    code = _code(notebook)

    assert 'globals().get("application")' in code
    assert "previous_application.close()" in code
    assert "local uses deterministic embeddings" in lower_markdown
    assert "live uses openai embeddings" in lower_markdown
    assert "local and live require an openai key unless a model is supplied" in lower_markdown
    assert "local and live use mem0 when its key is configured" in lower_markdown
    assert "local and live enable langfuse when both keys are configured" in lower_markdown


def test_production_mirror_notebook_requires_real_indexing_and_truthful_tracing_contracts():
    notebook = _read_notebook()
    code = _code(notebook)

    assert "initialize_data=False" in code
    assert "assert first_publish.records.created > 0" in code
    assert "assert first_publish.chunks.created > 0" in code
    assert "assert first_publish.graph_nodes.created > 0" in code
    assert "assert first_publish.relationships.created > 0" in code
    assert 'print("FIRST_PUBLISH "' in code
    assert 'print("SECOND_PUBLISH "' in code

    assert "application.run_react(" in code
    assert "application.react_agents.run(" not in code
    assert "react_trace_reference = application.trace_reference(react_result)" in code
    assert "assert react_trace_reference.trace_id" in code
    assert 'print("TRACE_REFERENCE "' in code
    assert "Structured execution summary is separate from this application trace" in code
    assert 'standards_tools == ["assess_standard_evidence"]' in code
    assert "standards_response = application.workflow.invoke(" in code


def test_production_mirror_notebook_distinguishes_portable_empty_start_from_persistent_stores():
    notebook = _read_notebook()
    markdown = _markdown(notebook).lower()
    code = _code(notebook)

    assert "portable starts with empty in-process stores for this demonstration" in markdown
    assert "local and live preserve existing records" in markdown
    assert 'print("Portable runtime assembled with empty in-process stores.")' in code
    assert 'print("External runtime assembled; existing persistent data was preserved.")' in code

    for section in ("records", "chunks", "graph_nodes", "relationships"):
        expected_total = (
            f"first_publish.{section}.created + first_publish.{section}.updated "
            f"+ first_publish.{section}.unchanged"
        )
        assert expected_total in code


def test_production_mirror_notebook_executes_headlessly_in_portable_mode(monkeypatch):
    monkeypatch.setenv("COPILOT_NOTEBOOK_MODE", "portable")
    for name in (
        "OPENAI_API_KEY",
        "MEM0_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    notebook = _read_notebook()
    executed = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute(cwd=str(ROOT), env={**os.environ, "COPILOT_NOTEBOOK_MODE": "portable"})

    output_text = "\n".join(
        str(output.get("text", ""))
        for cell in executed.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "stream"
    )
    assert "PRODUCTION_MIRROR_OK" in output_text
    assert "requested_mode=portable" in output_text
    assert "fallback_allowed=False" in output_text

    first_line = next(
        line for line in output_text.splitlines() if line.startswith("FIRST_PUBLISH ")
    )
    second_line = next(
        line for line in output_text.splitlines() if line.startswith("SECOND_PUBLISH ")
    )
    first_publish = json.loads(first_line.removeprefix("FIRST_PUBLISH "))
    second_publish = json.loads(second_line.removeprefix("SECOND_PUBLISH "))

    for section in ("records", "chunks", "graph_nodes", "relationships"):
        assert first_publish[section]["created"] > 0
        assert second_publish[section]["created"] == 0
        assert second_publish[section]["updated"] == 0
        assert second_publish[section]["unchanged"] > 0

    trace_line = next(
        line for line in output_text.splitlines() if line.startswith("TRACE_REFERENCE ")
    )
    trace_reference = json.loads(trace_line.removeprefix("TRACE_REFERENCE "))
    assert trace_reference["provider"] == "local"
    assert trace_reference["trace_id"].startswith("local-run-")
    assert trace_reference["url"] is None
    for label in ("fast_rag", "graph_rag", "agentic_workflow"):
        line = next(
            item for item in output_text.splitlines() if item.startswith(f"{label} trace_id=")
        )
        assert "local-run-" in line
    assert "Structured execution summary is separate from this application trace" in output_text

    route_line = next(
        line for line in output_text.splitlines() if line.startswith("ROUTE_EVAL_MATRIX ")
    )
    route_matrix = json.loads(route_line.removeprefix("ROUTE_EVAL_MATRIX "))
    assert set(route_matrix) == {"rag", "graph_rag", "agentic_rag"}
    assert len({item["question"] for item in route_matrix.values()}) == 3
    for expected_route, item in route_matrix.items():
        assert item["route"] == expected_route
        assert item["grounded"] is True
        assert item["citation_ids"]
        assert item["evaluation_passed"] is True
        assert item["citation_coverage"] == 1.0
