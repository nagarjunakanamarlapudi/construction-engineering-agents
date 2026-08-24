from civil_copilot.config import Settings


def test_settings_use_safe_local_defaults(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "MEM0_API_KEY",
        "DATABASE_URL",
        "QDRANT_URL",
        "NEO4J_URI",
        "API_PORT",
        "COPILOT_API_URL",
        "COPILOT_PUBLIC_API_URL",
        "AGENT_MODEL_REQUEST_TIMEOUT_SECONDS",
        "AGENT_REASONING_EFFORT",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is None
    assert settings.mem0_api_key is None
    assert settings.api_port == 8011
    assert settings.api_base_url == "http://127.0.0.1:8011"
    assert settings.public_api_base_url == "http://127.0.0.1:8011"
    assert settings.agent_max_seconds == 60.0
    assert settings.agent_model_request_timeout_seconds == 28.0
    assert settings.agent_reasoning_effort == "low"
    database_host = settings.database_url.hosts()[0]
    assert database_host["host"] == "localhost"
    assert database_host["port"] == 55432
    assert str(settings.qdrant_url) == "http://localhost:6333/"
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert str(settings.langfuse_base_url) == "http://localhost:3000/"


def test_explicit_copilot_api_url_overrides_the_local_port(monkeypatch):
    monkeypatch.setenv("API_PORT", "8123")
    monkeypatch.setenv("COPILOT_API_URL", "http://127.0.0.1:8999")

    settings = Settings(_env_file=None)

    assert settings.api_port == 8123
    assert settings.api_base_url == "http://127.0.0.1:8999"


def test_public_api_url_is_separate_from_the_internal_service_url(monkeypatch):
    monkeypatch.setenv("COPILOT_API_URL", "http://api:8011")
    monkeypatch.setenv("COPILOT_PUBLIC_API_URL", "http://127.0.0.1:8011")

    settings = Settings(_env_file=None)

    assert settings.api_base_url == "http://api:8011"
    assert settings.public_api_base_url == "http://127.0.0.1:8011"


def test_settings_read_secrets_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-secret")
    monkeypatch.setenv("MEM0_API_KEY", "test-mem0-secret")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "test-openai-secret"
    assert settings.mem0_api_key.get_secret_value() == "test-mem0-secret"
    assert "test-openai-secret" not in repr(settings)
    assert "test-mem0-secret" not in repr(settings)


def test_settings_parses_explicit_runtime_mode_without_inference(monkeypatch):
    monkeypatch.setenv("COPILOT_RUNTIME_MODE", "local")

    settings = Settings(_env_file=None)

    assert settings.copilot_runtime_mode == "local"
