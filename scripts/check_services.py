#!/usr/bin/env python3
"""Read-only local service health checks."""

from __future__ import annotations

import json
from typing import Any

import httpx
import psycopg
from neo4j import GraphDatabase

from civil_copilot.config import Settings


def check_services(settings: Settings) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    try:
        with psycopg.connect(str(settings.database_url), connect_timeout=3) as connection:
            value = connection.execute("SELECT 1").fetchone()[0]
        results["postgres"] = {"healthy": value == 1, "port": 55432}
    except Exception as error:  # health utility must report every service
        results["postgres"] = {"healthy": False, "error": type(error).__name__, "port": 55432}

    try:
        response = httpx.get(f"{str(settings.qdrant_url).rstrip('/')}/readyz", timeout=3)
        results["qdrant"] = {"healthy": response.is_success, "port": 6333}
    except Exception as error:
        results["qdrant"] = {"healthy": False, "error": type(error).__name__, "port": 6333}

    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
        )
        driver.verify_connectivity()
        driver.close()
        results["neo4j"] = {"healthy": True, "port": 7687}
    except Exception as error:
        results["neo4j"] = {"healthy": False, "error": type(error).__name__, "port": 7687}

    try:
        response = httpx.get("http://localhost:3000/api/public/health", timeout=3)
        results["langfuse"] = {
            "healthy": response.is_success,
            "port": 3000,
            "optional": True,
        }
    except Exception as error:
        results["langfuse"] = {
            "healthy": False,
            "error": type(error).__name__,
            "port": 3000,
            "optional": True,
        }
    return results


def main() -> int:
    results = check_services(Settings())
    print(json.dumps(results, indent=2, sort_keys=True))
    required_healthy = all(results[name]["healthy"] for name in ("postgres", "qdrant", "neo4j"))
    return 0 if required_healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
