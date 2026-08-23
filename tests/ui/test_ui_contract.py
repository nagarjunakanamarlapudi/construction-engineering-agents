from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_ui_contains_required_demo_surfaces():
    source = (ROOT / "src" / "civil_copilot" / "ui" / "app.py").read_text(encoding="utf-8")

    required_labels = [
        "Project Copilot",
        "Try a guided scenario",
        "Route",
        "Plan & tool trace",
        "Evidence & citations",
        "Project graph",
        "Evaluation",
        "Impact Explorer",
        "Revision & Evidence Lab",
        "Quality Control Room",
        "SYNTHETIC — ACADEMIC DEMO",
        "Official public preview",
        "Preference Memory",
        "Remember preferences",
        "st.chat_message",
        "st.chat_input",
    ]
    for label in required_labels:
        assert label in source
