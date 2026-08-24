from civil_copilot import runtime as runtime_module
from civil_copilot.api import main
from civil_copilot.config import Settings
from civil_copilot.runtime import RuntimeMode


def test_mem0_configuration_uses_api_key_scope_and_ignores_legacy_names(monkeypatch):
    attempts = []
    indexes = []

    class FakeIndex:
        def __init__(self, database_url):
            self.database_url = database_url
            indexes.append(self)

    class FakeBackend:
        def __init__(self, api_key, preference_index):
            attempts.append((api_key, preference_index))

        def put(self, _user_id, _project_id, _preference_type, _value):
            return None

        def list(self, _user_id, _project_id):
            return {}

    monkeypatch.setattr(main, "Mem0PreferenceBackend", FakeBackend)
    monkeypatch.setattr(main, "PostgresPreferenceIdIndex", FakeIndex)
    settings = Settings(
        _env_file=None,
        mem0_api_key="mem0-test",
        mem0_org_id="placeholder-org",
        mem0_project_id="placeholder-project",
    )

    memory = main.build_memory(settings)

    assert len(indexes) == 1
    assert indexes[0].database_url == str(settings.database_url)
    assert attempts == [("mem0-test", indexes[0])]
    assert isinstance(memory.backend, FakeBackend)


def test_local_runtime_uses_the_durable_three_part_preference_index(monkeypatch):
    calls = {}

    class FakeIndex:
        def __init__(self, database_url):
            calls["database_url"] = database_url

    class FakeBackend:
        def __init__(self, api_key, preference_index):
            calls["backend"] = (api_key, preference_index)

        def put(self, _user_id, _project_id, _preference_type, _value):
            return None

        def list(self, _user_id, _project_id):
            return {}

    monkeypatch.setattr(runtime_module, "PostgresPreferenceIdIndex", FakeIndex)
    monkeypatch.setattr(runtime_module, "Mem0PreferenceBackend", FakeBackend)
    settings = Settings(_env_file=None, mem0_api_key="mem0-test")

    memory = runtime_module._application_memory(settings, RuntimeMode.LOCAL)

    assert calls["database_url"] == str(settings.database_url)
    assert calls["backend"][0] == "mem0-test"
    assert isinstance(calls["backend"][1], FakeIndex)
    assert isinstance(memory.backend, FakeBackend)
