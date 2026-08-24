import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_make_api_uses_the_non_conflicting_copilot_port():
    result = subprocess.run(
        ["/usr/bin/make", "-n", "api"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--port 8011" in result.stdout


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
    assert "COPY sql ./sql" in dockerfile


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


def test_compose_defines_healthy_api_and_ui_with_service_dependencies():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["api"]["ports"] == ["127.0.0.1:8011:8011"]
    assert services["ui"]["ports"] == ["127.0.0.1:8501:8501"]
    assert services["api"]["depends_on"] == {
        "postgres": {"condition": "service_healthy"},
        "qdrant": {"condition": "service_healthy"},
        "neo4j": {"condition": "service_healthy"},
    }
    assert services["ui"]["depends_on"] == {"api": {"condition": "service_healthy"}}
    assert services["api"]["environment"]["QDRANT_URL"] == "http://qdrant:6333"
    assert services["api"]["environment"]["RERANKER_FAILURE_POLICY"] == ("heuristic_fallback")
    assert services["ui"]["environment"]["COPILOT_API_URL"] == "http://api:8011"
    assert services["ui"]["environment"]["COPILOT_PUBLIC_API_URL"] == "http://127.0.0.1:8011"
    assert "healthcheck" in services["api"]
    assert "healthcheck" in services["ui"]


def test_observability_web_ui_is_bound_to_loopback():
    compose = yaml.safe_load((ROOT / "compose.observability.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["langfuse-web"]["ports"] == ["127.0.0.1:3000:3000"]
    assert "http://langfuse-web:3000/api/public/health" in " ".join(
        compose["services"]["langfuse-web"]["healthcheck"]["test"]
    )


def test_make_up_and_down_manage_the_complete_local_application():
    up = subprocess.run(
        ["/usr/bin/make", "-n", "up"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    down = subprocess.run(
        ["/usr/bin/make", "-n", "down"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "postgres qdrant neo4j api ui" in up
    assert "docker compose down" in down


def test_operational_api_and_live_eval_commands_select_non_portable_modes():
    root = Path(__file__).parents[2]
    api = subprocess.run(
        ["/usr/bin/make", "-n", "api"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    live_eval = subprocess.run(
        ["/usr/bin/make", "-n", "eval-live"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "COPILOT_RUNTIME_MODE=live" in api
    assert "COPILOT_RUNTIME_MODE=live" in live_eval


def test_make_e2e_includes_the_deterministic_portable_production_route_matrix():
    command = subprocess.run(
        ["/usr/bin/make", "-n", "e2e"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "tests/e2e" in command


def test_make_exposes_repeatable_portable_and_live_e2e_workflows():
    portable = subprocess.run(
        ["/usr/bin/make", "-n", "e2e"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    live = subprocess.run(
        ["/usr/bin/make", "-n", "e2e-live"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "jupyter nbconvert --execute" in portable
    assert "civil_copilot.evals.runner" in portable
    assert "tests/e2e" in portable
    assert "docker compose up -d --build" in live
    assert "scripts/check_services.py" in live
    assert "scripts/ingest.py" in live
    assert "tests/integration" in live
    assert "--live" in live
