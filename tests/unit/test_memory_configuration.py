from civil_copilot.api import main
from civil_copilot.config import Settings


def test_mem0_configuration_uses_api_key_scope_and_ignores_legacy_names(monkeypatch):
    attempts = []

    class FakeBackend:
        def __init__(self, api_key):
            attempts.append(api_key)

        def put(self, _user_id, _project_id, _preference_type, _value):
            return None

        def list(self, _user_id, _project_id):
            return {}

    monkeypatch.setattr(main, "Mem0PreferenceBackend", FakeBackend)
    settings = Settings(
        _env_file=None,
        mem0_api_key="mem0-test",
        mem0_org_id="placeholder-org",
        mem0_project_id="placeholder-project",
    )

    memory = main.build_memory(settings)

    assert attempts == ["mem0-test"]
    assert isinstance(memory.backend, FakeBackend)
