import json
import os
import re
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "10_langchain_middleware_primer.ipynb"


def _read_notebook():
    return nbformat.read(NOTEBOOK, as_version=4)


def _stream_text(notebook) -> str:
    return "\n".join(
        str(output.get("text", ""))
        for cell in notebook.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "stream"
    )


def test_middleware_primer_is_domain_neutral_and_uses_readable_visuals():
    """Removing the domain boundary or lifecycle visual must break this test."""
    notebook = _read_notebook()
    markdown = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")

    assert notebook.metadata["middleware_primer"] is True
    assert notebook.metadata["domain_neutral"] is True
    assert "civil engineering" not in markdown.lower()

    for image_path in (
        "../docs/images/middleware-agent-lifecycle.svg",
        "../docs/images/middleware-capability-map.svg",
    ):
        assert image_path in markdown
        assert (NOTEBOOK.parent / image_path).resolve().is_file()


def test_middleware_primer_executes_the_real_create_agent_lifecycle_model_free():
    """Breaking a hook, built-in middleware example, or final eval must break this test."""
    notebook = _read_notebook()
    clean_env = {
        **os.environ,
        "MIDDLEWARE_PRIMER_MODE": "model_free",
        "MIDDLEWARE_PRIMER_LOAD_DOTENV": "0",
        "MIDDLEWARE_PRIMER_AUTO_REVIEW": "1",
    }
    clean_env.pop("OPENAI_API_KEY", None)

    executed = NotebookClient(
        notebook,
        timeout=240,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute(cwd=str(ROOT), env=clean_env)
    output_text = _stream_text(executed)

    expected_events = [
        "before_agent",
        "before_model",
        "wrap_model_call.before",
        "wrap_model_call.after",
        "after_model",
        "wrap_tool_call.before:lookup_status",
        "wrap_tool_call.after:lookup_status",
        "before_model",
        "wrap_model_call.before",
        "wrap_model_call.after",
        "after_model",
        "after_agent",
    ]
    event_line = next(
        line for line in output_text.splitlines() if line.startswith("LIFECYCLE_EVENTS ")
    )
    assert json.loads(event_line.removeprefix("LIFECYCLE_EVENTS ")) == expected_events

    for expected in (
        "LIFECYCLE_ORDER_OK True",
        "TOOL_RETRY_OK True",
        "MODEL_FALLBACK_OK True",
        "TOOL_LIMIT_ENFORCED True",
        "PII_REDACTED True",
        "HITL_PAUSED True",
        "HITL_APPROVED True",
        "EVALUATION_PASS_RATE 1.00",
        "MIDDLEWARE_PRIMER_OK mode=model_free",
    ):
        assert expected in output_text

    assert not re.search(r"(?:sk-|m0-|mem0-)[A-Za-z0-9_-]{12,}", output_text)


def test_middleware_primer_provider_factory_selects_ollama_and_openai():
    """Changing either documented provider mode to the wrong model must break this test."""
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

    namespace = {
        "ChatOllama": fake_ollama,
        "ChatOpenAI": fake_openai,
        "LifecycleScriptModel": lambda: object(),
    }
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
