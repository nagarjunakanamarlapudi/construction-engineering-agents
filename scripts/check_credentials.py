#!/usr/bin/env python3
"""Validate configured managed-service credentials without printing account data."""

from __future__ import annotations

import json

import httpx

from civil_copilot.config import Settings


def _status(configured: bool, response: httpx.Response | None = None) -> str:
    if not configured:
        return "missing"
    return "valid" if response and response.is_success else "rejected"


def main() -> int:
    settings = Settings()
    results: dict[str, str] = {}
    openai_response = None
    if settings.openai_api_key:
        openai_response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
            timeout=10,
        )
    results["openai"] = _status(bool(settings.openai_api_key), openai_response)

    mem0_response = None
    if settings.mem0_api_key:
        mem0_response = httpx.get(
            "https://api.mem0.ai/api/v1/orgs/organizations/",
            headers={"Authorization": f"Token {settings.mem0_api_key.get_secret_value()}"},
            timeout=10,
        )
    results["mem0"] = _status(bool(settings.mem0_api_key), mem0_response)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(value == "valid" for value in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
