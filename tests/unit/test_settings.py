from civil_copilot.config import Settings


def test_settings_use_safe_local_defaults(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "MEM0_API_KEY",
        "DATABASE_URL",
        "QDRANT_URL",
        "NEO4J_URI",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is None
    assert settings.mem0_api_key is None
    database_host = settings.database_url.hosts()[0]
    assert database_host["host"] == "localhost"
    assert database_host["port"] == 55432
    assert str(settings.qdrant_url) == "http://localhost:6333/"
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert str(settings.langfuse_base_url) == "http://localhost:3000/"


def test_settings_read_secrets_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-secret")
    monkeypatch.setenv("MEM0_API_KEY", "test-mem0-secret")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "test-openai-secret"
    assert settings.mem0_api_key.get_secret_value() == "test-mem0-secret"
    assert "test-openai-secret" not in repr(settings)
    assert "test-mem0-secret" not in repr(settings)
