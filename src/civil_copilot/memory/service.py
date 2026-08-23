"""Mem0 boundary: remember user preferences, never project truth or generated answers."""

from __future__ import annotations

import re
from typing import Protocol

from mem0 import MemoryClient

PROJECT_IDENTIFIER = re.compile(r"\b(?:RFI|NCR|ACT|DRAW|PIECE|WELD|INSP|PO|MTC)-[A-Z0-9-]+\b", re.I)
ALLOWED_PREFERENCES: dict[str, set[str]] = {
    "preferred_units": {"metric", "si", "imperial"},
    "answer_style": {"concise", "detailed", "plain_language"},
    "citation_detail": {"compact", "expanded"},
    "preferred_route": {"auto", "rag", "graph_rag", "agentic_rag"},
}


class PreferenceBackend(Protocol):
    def put(self, user_id: str, project_id: str, preference_type: str, value: str) -> None: ...

    def list(self, user_id: str, project_id: str) -> dict[str, str]: ...


class InMemoryPreferenceBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], str] = {}

    def put(self, user_id: str, project_id: str, preference_type: str, value: str) -> None:
        self.values[(user_id, project_id, preference_type)] = value

    def list(self, user_id: str, project_id: str) -> dict[str, str]:
        return {
            preference_type: value
            for (stored_user, stored_project, preference_type), value in self.values.items()
            if stored_user == user_id and stored_project == project_id
        }


class Mem0PreferenceBackend:
    """Managed Mem0 adapter using metadata-scoped records."""

    def __init__(
        self,
        api_key: str,
    ) -> None:
        self.client = MemoryClient(api_key=api_key)

    def put(self, user_id: str, project_id: str, preference_type: str, value: str) -> None:
        self.client.add(
            [{"role": "user", "content": f"Preference {preference_type}: {value}"}],
            user_id=user_id,
            metadata={
                "memory_kind": "user_preference",
                "project_id": project_id,
                "preference_type": preference_type,
                "preference_value": value,
            },
            infer=False,
        )

    def list(self, user_id: str, project_id: str) -> dict[str, str]:
        response = self.client.get_all(
            filters={
                "AND": [
                    {"user_id": user_id},
                    {"metadata": {"memory_kind": "user_preference"}},
                    {"metadata": {"project_id": project_id}},
                ]
            },
            page=1,
            page_size=100,
        )
        rows = response.get("results", response) if isinstance(response, dict) else response
        preferences: dict[str, str] = {}
        for row in rows or []:
            metadata = row.get("metadata", {})
            preference_type = metadata.get("preference_type")
            value = metadata.get("preference_value")
            if preference_type in ALLOWED_PREFERENCES and isinstance(value, str):
                preferences[preference_type] = value
        return preferences


class PreferenceMemory:
    def __init__(self, backend: PreferenceBackend) -> None:
        self.backend = backend

    def add(
        self,
        user_id: str,
        project_id: str,
        preference_type: str,
        value: str,
    ) -> None:
        allowed_values = ALLOWED_PREFERENCES.get(preference_type)
        normalized = value.strip().lower()
        if (
            not allowed_values
            or normalized not in allowed_values
            or PROJECT_IDENTIFIER.search(value)
        ):
            raise ValueError(
                "Memory accepts only an allowlisted user preference, never project facts or answers"
            )
        self.backend.put(user_id, project_id, preference_type, normalized)

    def get(self, user_id: str, project_id: str) -> dict[str, str]:
        return dict(sorted(self.backend.list(user_id, project_id).items()))
