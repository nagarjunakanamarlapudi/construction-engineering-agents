import operator
import os
import re
from pathlib import Path
from typing import Annotated

import nbformat
from IPython.display import HTML, Image
from langgraph.graph import END, START, StateGraph
from nbclient import NotebookClient
from typing_extensions import TypedDict

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "09_langchain_langgraph_state_memory_primer.ipynb"


def _read_notebook():
    return nbformat.read(NOTEBOOK, as_version=4)


def test_graph_display_utility_renders_compiled_langgraph_as_an_image(tmp_path):
    """Removing the compiled-graph render/display boundary must break this test."""
    notebook = _read_notebook()
    utility_cell = next(
        cell.source
        for cell in notebook.cells
        if cell.cell_type == "code" and "def display_graph" in cell.source
    )
    displayed: list[object] = []
    namespace = {"HTML": HTML, "Image": Image, "display": displayed.append}
    exec(utility_cell, namespace)  # noqa: S102 - execute one isolated notebook utility cell

    png = b"\x89PNG\r\n\x1a\n"
    render_calls: list[dict] = []

    class DrawableGraph:
        def draw_mermaid_png(self, **kwargs):
            render_calls.append(kwargs)
            return png

    class CompiledGraph:
        def get_graph(self, *, xray=False):
            assert xray is True
            return DrawableGraph()

    output_path = tmp_path / "calculation-graph.png"
    image = namespace["display_graph"](
        CompiledGraph(),
        xray=True,
        output_file_path=output_path,
    )

    assert isinstance(image, Image)
    assert image.data == png
    assert displayed[-1] is image
    assert render_calls == [{"output_file_path": str(output_path)}]


def test_part_one_displays_the_compiled_calculation_graph():
    """Removing the Part 1 utility call must break this test."""
    notebook = _read_notebook()
    part_one_cell = next(
        cell.source
        for cell in notebook.cells
        if cell.cell_type == "code" and "calculation_builder = StateGraph" in cell.source
    )
    displayed_graphs: list[object] = []
    namespace = {
        "Annotated": Annotated,
        "END": END,
        "START": START,
        "StateGraph": StateGraph,
        "TypedDict": TypedDict,
        "display_graph": displayed_graphs.append,
        "operator": operator,
        "table": lambda _rows: None,
    }

    exec(part_one_cell, namespace)  # noqa: S102 - execute the isolated Part 1 cell

    assert displayed_graphs == [namespace["calculation_graph"]]


def test_state_memory_primer_has_domain_neutral_visual_assets():
    notebook = _read_notebook()
    markdown = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")

    assert notebook.metadata["state_memory_primer"] is True
    assert notebook.metadata["domain_neutral"] is True
    assert "civil engineering" not in markdown.lower()

    for image_path in (
        "../docs/images/state-memory-primer-mental-model.png",
        "../docs/images/state-memory-primer-thread-boundaries.png",
        "../docs/images/state-memory-primer-hitl-lifecycle.png",
        "../docs/images/state-memory-primer-execution-modes.png",
    ):
        assert image_path in markdown
        assert (NOTEBOOK.parent / image_path).resolve().is_file()


def test_state_memory_primer_executes_complete_model_free_lifecycle():
    notebook = _read_notebook()
    clean_env = {
        **os.environ,
        "STATE_MEMORY_PRIMER_MODE": "model_free",
        "STATE_MEMORY_PRIMER_LOAD_DOTENV": "0",
    }
    clean_env.pop("OPENAI_API_KEY", None)

    executed = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute(cwd=str(ROOT), env=clean_env)

    output_text = "\n".join(
        str(output.get("text", ""))
        for cell in executed.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "stream"
    )
    for expected in (
        "STATE_TOTAL 7",
        "SAME_THREAD_TURNS 2",
        "DIFFERENT_THREAD_ISOLATED True",
        "CHECKPOINT_HISTORY_AVAILABLE True",
        "CROSS_THREAD_MEMORY concise",
        "UPDATED_MEMORY detailed",
        "HITL_PAUSED True",
        "HITL_APPROVED True",
        "HITL_EDITED True",
        "HITL_REJECTED True",
        "EVALUATION_PASS_RATE 1.00",
        "STATE_MEMORY_PRIMER_OK mode=model_free",
    ):
        assert expected in output_text

    assert not re.search(r"(?:sk-|m0-|mem0-)[A-Za-z0-9_-]{12,}", output_text)


def test_provider_factory_selects_requested_ollama_and_openai_models(monkeypatch):
    notebook = _read_notebook()
    factory_cell = next(
        cell.source
        for cell in notebook.cells
        if cell.cell_type == "code" and "def build_chat_model" in cell.source
    )
    calls: list[tuple[str, dict]] = []

    def fake_ollama(**kwargs):
        calls.append(("ollama", kwargs))
        return object()

    def fake_openai(**kwargs):
        calls.append(("openai", kwargs))
        return object()

    namespace = {"ChatOllama": fake_ollama, "ChatOpenAI": fake_openai}
    exec(factory_cell, namespace)  # noqa: S102 - execute one isolated notebook factory cell

    namespace["build_chat_model"]("ollama_gemma4")
    namespace["build_chat_model"]("openai")

    assert calls == [
        (
            "ollama",
            {
                "model": "gemma4:e4b",
                "temperature": 0,
                "validate_model_on_init": True,
            },
        ),
        (
            "openai",
            {
                "model": "gpt-5-mini",
                "reasoning_effort": "low",
                "timeout": 30,
                "max_retries": 0,
            },
        ),
    ]
