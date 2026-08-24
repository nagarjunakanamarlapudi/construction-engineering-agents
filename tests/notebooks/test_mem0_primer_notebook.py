import os
import re
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "08_mem0_primer.ipynb"


def _read_notebook():
    return nbformat.read(NOTEBOOK, as_version=4)


def _code(notebook) -> str:
    return "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")


def _markdown(notebook) -> str:
    return "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")


def test_mem0_primer_is_domain_neutral_and_covers_the_full_memory_lifecycle():
    notebook = _read_notebook()
    markdown = _markdown(notebook)
    code = _code(notebook)

    assert notebook.metadata["mem0_primer"] is True
    assert "civil engineering" not in markdown.lower()
    assert "civil_copilot" not in code

    for concept in (
        "What Mem0 is",
        "What Mem0 is not",
        "infer=True",
        "infer=False",
        "Hybrid ownership",
        "user_id",
        "agent_id",
        "app_id",
        "run_id",
        "memory ID",
        "update",
        "history",
        "delete",
        "Evaluation",
        "Privacy",
    ):
        assert concept in markdown

    for image_path in (
        "../docs/images/mem0-primer-mental-model.png",
        "../docs/images/mem0-primer-three-strategies.png",
        "../docs/images/mem0-primer-lifecycle.png",
        "../docs/images/mem0-primer-deployment-modes.png",
    ):
        assert image_path in markdown
        assert (NOTEBOOK.parent / image_path).resolve().is_file()

    for symbol in (
        "Memory",
        "MemoryClient",
        "QdrantClient",
        'location=\":memory:\"',
        'history_db_path\": \":memory:\"',
        "infer=False",
        "infer=True",
        ".add(",
        ".search(",
        ".get(",
        ".update(",
        ".history(",
        ".delete(",
    ):
        assert symbol in code

    assert "MEM0_PRIMER_MODE" in code
    for mode in ("offline", "oss_openai", "oss_ollama", "platform"):
        assert mode in code
    assert "load_dotenv" in code
    assert "OPENAI_API_KEY" in code
    assert "MEM0_API_KEY" in code
    assert "pip install" not in code
    assert "%pip" not in code
    assert not re.search(r"(?:sk-|m0-|mem0-)[A-Za-z0-9_-]{12,}", code)


def test_mem0_primer_executes_offline_without_credentials_and_uses_real_mem0_oss():
    notebook = _read_notebook()
    clean_env = {
        **os.environ,
        "MEM0_PRIMER_MODE": "offline",
        "MEM0_PRIMER_LOAD_DOTENV": "0",
    }
    clean_env.pop("OPENAI_API_KEY", None)
    clean_env.pop("MEM0_API_KEY", None)

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
    assert "MEM0_PRIMER_OK" in output_text
    assert "mode=offline" in output_text
    assert "selected_backend=mem0_oss_qdrant_ram" in output_text
    assert "first_value=concise" in output_text
    assert "updated_value=detailed" in output_text
    assert "history_entries=" in output_text
    assert "deleted=True" in output_text
    assert not re.search(r"(?:sk-|m0-|mem0-)[A-Za-z0-9_-]{12,}", output_text)


def test_mem0_primer_openai_extraction_config_uses_model_supported_defaults(monkeypatch):
    notebook = _read_notebook()
    builder_cell = next(
        cell.source
        for cell in notebook.cells
        if cell.cell_type == "code" and "def build_in_memory_oss" in cell.source
    )
    captured = {}

    class FakeMemory:
        @staticmethod
        def from_config(config):
            captured.update(config)
            return object()

    namespace = {
        "Memory": FakeMemory,
        "QdrantClient": lambda **_kwargs: object(),
        "FakeListChatModel": lambda **_kwargs: object(),
        "DeterministicFakeEmbedding": lambda **_kwargs: object(),
        "uuid4": __import__("uuid").uuid4,
    }
    exec(builder_cell, namespace)
    namespace["build_in_memory_oss"]("oss_openai")

    assert captured["llm"]["config"] == {
        "model": "gpt-5-mini",
        "is_reasoning_model": True,
        "reasoning_effort": "low",
    }
