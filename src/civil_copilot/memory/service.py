"""Mem0 boundary: remember user preferences, never project truth or generated answers."""

from __future__ import annotations

import re
from typing import Any, Protocol

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


class PreferenceIdIndex(Protocol):
    """Map one application preference key to its Mem0-generated identifier."""

    def get(self, user_id: str, project_id: str, preference_type: str) -> str | None: ...

    def put(
        self,
        user_id: str,
        project_id: str,
        preference_type: str,
        memory_id: str,
    ) -> None: ...


class InMemoryPreferenceIdIndex:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], str] = {}

    def get(self, user_id: str, project_id: str, preference_type: str) -> str | None:
        return self.values.get((user_id, project_id, preference_type))

    def put(
        self,
        user_id: str,
        project_id: str,
        preference_type: str,
        memory_id: str,
    ) -> None:
        self.values[(user_id, project_id, preference_type)] = memory_id


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
        preference_index: PreferenceIdIndex | None = None,
    ) -> None:
        self.client = MemoryClient(api_key=api_key)
        self.preference_index = preference_index or InMemoryPreferenceIdIndex()

    @staticmethod
    def _metadata(project_id: str, preference_type: str, value: str) -> dict[str, str]:
        return {
            "memory_kind": "user_preference",
            "project_id": project_id,
            "preference_type": preference_type,
            "preference_value": value,
        }

    @staticmethod
    def _added_memory_id(response: Any) -> str:
        if isinstance(response, dict) and isinstance(response.get("id"), str):
            return response["id"]
        results = response.get("results") if isinstance(response, dict) else None
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and isinstance(result.get("id"), str):
                    return result["id"]
        raise RuntimeError("Mem0 add response did not contain a memory id")

    def put(self, user_id: str, project_id: str, preference_type: str, value: str) -> None:
        metadata = self._metadata(project_id, preference_type, value)
        text = f"Preference {preference_type}: {value}"
        memory_id = self.preference_index.get(user_id, project_id, preference_type)
        if memory_id is not None:
            self.client.update(memory_id, text=text, metadata=metadata)
            return
        response = self.client.add(
            [{"role": "user", "content": f"Preference {preference_type}: {value}"}],
            user_id=user_id,
            metadata=metadata,
            infer=False,
        )
        self.preference_index.put(
            user_id,
            project_id,
            preference_type,
            self._added_memory_id(response),
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
