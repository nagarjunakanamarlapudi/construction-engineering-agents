#!/usr/bin/env python3
"""Validate configured managed-service credentials without printing account data."""

from __future__ import annotations

import json

import httpx
from mem0 import MemoryClient

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
        try:
            openai_response = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
                timeout=10,
            )
        except httpx.HTTPError:
            openai_response = None
    results["openai"] = _status(bool(settings.openai_api_key), openai_response)

    mem0_valid = False
    if settings.mem0_api_key:
        try:
            client = MemoryClient(api_key=settings.mem0_api_key.get_secret_value())
            client.get_all(
                filters={"user_id": "civil-copilot-credential-check"},
                page=1,
                page_size=1,
            )
            mem0_valid = True
        except Exception:  # credential utility reports a status without leaking SDK details
            mem0_valid = False
    results["mem0"] = "valid" if mem0_valid else "rejected" if settings.mem0_api_key else "missing"
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(value == "valid" for value in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
