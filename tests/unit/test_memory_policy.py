import pytest

from civil_copilot.memory import service
from civil_copilot.memory.service import (
    InMemoryPreferenceBackend,
    InMemoryPreferenceIdIndex,
    Mem0PreferenceBackend,
    PreferenceMemory,
)


def test_memory_accepts_only_allowlisted_user_preferences_scoped_to_user_and_project():
    backend = InMemoryPreferenceBackend()
    memory = PreferenceMemory(backend)

    memory.add("user-1", "BLR-STEEL-DEMO", "preferred_units", "metric")
    memory.add("user-1", "BLR-STEEL-DEMO", "answer_style", "concise")

    assert memory.get("user-1", "BLR-STEEL-DEMO") == {
        "answer_style": "concise",
        "preferred_units": "metric",
    }
    assert memory.get("user-2", "BLR-STEEL-DEMO") == {}


@pytest.mark.parametrize(
    ("preference_type", "value"),
    [
        ("generated_answer", "The project is delayed"),
        ("project_status", "Activity A is 20 days late"),
        ("graph_edge", "RFI-087 AFFECTS ACT-STEEL-009"),
        ("source_text", "Copied standard or project document text"),
        ("preferred_units", "RFI-087 says the project is delayed"),
    ],
)
def test_memory_rejects_answers_project_facts_edges_and_source_text(preference_type, value):
    memory = PreferenceMemory(InMemoryPreferenceBackend())

    with pytest.raises(ValueError, match="preference"):
        memory.add("user-1", "BLR-STEEL-DEMO", preference_type, value)


def test_mem0_backend_uses_current_key_scoping_and_filter_contract(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def add(self, messages, **kwargs):
            calls["add"] = {"messages": messages, **kwargs}
            return {"results": [{"id": "mem-preference-1"}]}

        def get_all(self, **kwargs):
            calls["get_all"] = kwargs
            return {
                "results": [
                    {
                        "metadata": {
                            "memory_kind": "user_preference",
                            "project_id": "BLR-STEEL-DEMO",
                            "preference_type": "answer_style",
                            "preference_value": "plain_language",
                        }
                    }
                ]
            }

    monkeypatch.setattr(service, "MemoryClient", FakeClient)
    backend = Mem0PreferenceBackend("mem0-test")
    backend.put("reviewer", "BLR-STEEL-DEMO", "answer_style", "plain_language")
    preferences = backend.list("reviewer", "BLR-STEEL-DEMO")

    assert calls["init"] == {"api_key": "mem0-test"}
    assert calls["add"]["user_id"] == "reviewer"
    assert calls["get_all"] == {
        "filters": {
            "AND": [
                {"user_id": "reviewer"},
                {"metadata": {"memory_kind": "user_preference"}},
                {"metadata": {"project_id": "BLR-STEEL-DEMO"}},
            ]
        },
        "page": 1,
        "page_size": 100,
    }
    assert preferences == {"answer_style": "plain_language"}


def test_mem0_repeated_preference_save_updates_the_memory_bound_to_the_composite_key(
    monkeypatch,
):
    class StatefulClient:
        def __init__(self, **_kwargs):
            self.memories = {}
            self.add_count = 0
            self.update_count = 0

        def add(self, messages, **kwargs):
            self.add_count += 1
            memory_id = f"mem-{self.add_count}"
            self.memories[memory_id] = {
                "id": memory_id,
                "memory": messages[0]["content"],
                "metadata": kwargs["metadata"],
            }
            return {"results": [{"id": memory_id}]}

        def update(self, memory_id, **kwargs):
            self.update_count += 1
            self.memories[memory_id] = {
                "id": memory_id,
                "memory": kwargs["text"],
                "metadata": kwargs["metadata"],
            }
            return self.memories[memory_id]

        def get_all(self, **_kwargs):
            return {"results": list(self.memories.values())}

        def get(self, memory_id):
            return self.memories[memory_id]

    monkeypatch.setattr(service, "MemoryClient", StatefulClient)
    index = InMemoryPreferenceIdIndex()
    backend = Mem0PreferenceBackend("mem0-test", preference_index=index)

    backend.put("reviewer", "BLR-STEEL-DEMO", "answer_style", "concise")
    backend.put("reviewer", "BLR-STEEL-DEMO", "answer_style", "detailed")
    backend.put("reviewer", "OTHER-PROJECT", "answer_style", "plain_language")

    assert backend.client.add_count == 2
    assert backend.client.update_count == 1
    assert len(backend.client.memories) == 2
    assert index.get("reviewer", "BLR-STEEL-DEMO", "answer_style") == "mem-1"
    assert index.get("reviewer", "OTHER-PROJECT", "answer_style") == "mem-2"
    assert backend.client.memories["mem-1"]["metadata"] == {
        "memory_kind": "user_preference",
        "project_id": "BLR-STEEL-DEMO",
        "preference_type": "answer_style",
        "preference_value": "detailed",
    }
