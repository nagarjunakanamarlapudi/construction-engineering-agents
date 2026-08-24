from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[2]


def test_teaching_notebooks_import_production_modules_without_install_cells():
    notebooks = sorted((ROOT / "notebooks").glob("*.ipynb"))

    assert [path.name for path in notebooks] == [
        "01_rag_foundations.ipynb",
        "02_hybrid_reranking.ipynb",
        "03_graph_rag.ipynb",
        "04_agentic_rag.ipynb",
        "05_evaluations.ipynb",
        "06_educational_toy_end_to_end.ipynb",
        "07_production_mirror_end_to_end.ipynb",
    ]
    for path in notebooks:
        notebook = nbformat.read(path, as_version=4)
        source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
        if path.name != "06_educational_toy_end_to_end.ipynb":
            assert "civil_copilot" in source
        assert "pip install" not in source
        assert "%pip" not in source
