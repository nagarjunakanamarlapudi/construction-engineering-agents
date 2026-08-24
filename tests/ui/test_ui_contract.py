from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_ui_contains_required_demo_surfaces():
    source = (ROOT / "src" / "civil_copilot" / "ui" / "app.py").read_text(encoding="utf-8")

    required_labels = [
        "Project Copilot",
        "Project Command Center",
        "Current project",
        "Try a guided scenario",
        "Route",
        "What we found",
        "Why",
        "What is affected",
        "Supporting evidence",
        "Investigation details",
        "Plan & tool trace",
        "Evidence & citations",
        "Project graph",
        "Evaluation",
        "Impact Explorer",
        "Revision & Evidence Lab",
        "Quality Control Room",
        "Standards Evidence Review",
        "Run standards evidence review",
        "Project evidence (synthetic)",
        "BIS source (official preview)",
        "not a compliance certificate",
        "SYNTHETIC — ACADEMIC DEMO",
        "Official public preview",
        "Run impact investigation",
        "What changed",
        "Preference Memory",
        "Remember preferences",
        "st.chat_message",
        "st.chat_input",
    ]
    for label in required_labels:
        assert label in source


def test_streamlit_ui_reuses_one_conversation_id_for_all_workspace_actions():
    source = (ROOT / "src" / "civil_copilot" / "ui" / "app.py").read_text(encoding="utf-8")

    assert 'if "conversation_id" not in st.session_state' in source
    assert '"conversation_id": st.session_state.conversation_id' in source


def test_streamlit_ui_uses_public_api_base_for_browser_citation_links():
    source = (ROOT / "src" / "civil_copilot" / "ui" / "app.py").read_text(encoding="utf-8")

    assert "PUBLIC_API_BASE = Settings().public_api_base_url" in source
    assert "PUBLIC_API_BASE}/api/records/" in source


def test_streamlit_memory_uses_the_server_owned_default_demo_identity():
    source = (ROOT / "src" / "civil_copilot" / "ui" / "app.py").read_text(encoding="utf-8")

    assert "from civil_copilot.api.principal import DEFAULT_DEMO_USER_ID" in source
    assert "DEMO_USER_ID = DEFAULT_DEMO_USER_ID" in source
    assert 'DEMO_USER_ID = "demo-presenter"' not in source


def test_standards_matrix_uses_wrapping_reader_cards_instead_of_a_wide_table():
    app_source = (ROOT / "src" / "civil_copilot" / "ui" / "app.py").read_text(encoding="utf-8")
    theme_source = (ROOT / "src" / "civil_copilot" / "ui" / "theme.py").read_text(encoding="utf-8")

    assert 'class="standards-row"' in app_source
    assert 'class="standards-reason"' in app_source
    assert 'class="standards-sources"' in app_source
    assert ".standards-row" in theme_source
    assert ".standards-sources" in theme_source
