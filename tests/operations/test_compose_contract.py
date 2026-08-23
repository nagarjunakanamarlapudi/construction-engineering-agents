from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_persistent_healthy_data_services():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"postgres", "qdrant", "neo4j"} <= services.keys()
    assert services["postgres"]["ports"] == ["55432:5432"]
    assert services["qdrant"]["ports"] == ["6333:6333", "6334:6334"]
    assert services["neo4j"]["ports"] == ["7474:7474", "7687:7687"]
    for name in ("postgres", "qdrant", "neo4j"):
        assert "healthcheck" in services[name]
