from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_docker_context_excludes_secrets_and_local_build_artifacts():
    patterns = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in patterns
    assert ".venv" in patterns
    assert ".worktrees" in patterns
    assert ".git" in patterns
    assert "notebooks" in patterns


def test_dockerfile_copies_package_readme_before_installing_project():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY pyproject.toml uv.lock README.md ./" in dockerfile


def test_compose_defines_persistent_healthy_data_services():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"postgres", "qdrant", "neo4j"} <= services.keys()
    assert services["postgres"]["ports"] == ["127.0.0.1:55432:5432"]
    assert services["qdrant"]["ports"] == [
        "127.0.0.1:6333:6333",
        "127.0.0.1:6334:6334",
    ]
    assert services["neo4j"]["ports"] == [
        "127.0.0.1:7474:7474",
        "127.0.0.1:7687:7687",
    ]
    for name in ("postgres", "qdrant", "neo4j"):
        assert "healthcheck" in services[name]


def test_observability_web_ui_is_bound_to_loopback():
    compose = yaml.safe_load((ROOT / "compose.observability.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["langfuse-web"]["ports"] == ["127.0.0.1:3000:3000"]
