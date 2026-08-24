from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from civil_copilot.agents.state import ChatRequest
from civil_copilot.api.main import create_app
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.runtime import build_application_runtime


def test_portable_runtime_labels_process_local_checkpoints_as_non_durable():
    application = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        assert application.capabilities.checkpoint_backend == "memory"
        assert application.capabilities.durable_checkpoints is False
        assert application.checkpoints.durable is False
    finally:
        application.close()


def test_context_keeps_conversation_identity_but_rotates_request_identity():
    application = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        first = application.tool_context(
            "reviewer",
            "BLR-STEEL-DEMO",
            ("project:blr-steel-demo",),
            conversation_id="walkthrough-087",
        )
        second = application.tool_context(
            "reviewer",
            "BLR-STEEL-DEMO",
            ("project:blr-steel-demo",),
            conversation_id="walkthrough-087",
        )

        assert first.conversation_id == second.conversation_id == "walkthrough-087"
        assert first.request_id != second.request_id
        assert application.react_agents.thread_id("document", first) == (
            "project=BLR-STEEL-DEMO|user=reviewer|role=document|conversation=walkthrough-087|"
            "acl=dbbf93e70e160f3e"
        )
        assert application.react_agents.thread_id(
            "document", first
        ) == application.react_agents.thread_id("document", second)
    finally:
        application.close()


def test_same_client_conversation_handle_cannot_cross_user_or_project_boundaries():
    application = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        owner = replace(
            application.tool_context(
                "owner",
                "BLR-STEEL-DEMO",
                ("project:blr-steel-demo",),
            ),
            conversation_id="same-browser-handle",
        )
        other_user = replace(owner, user_id="other-user", request_id="other-request")
        other_project = replace(owner, project_id="OTHER-PROJECT", request_id="project-request")

        reduced_access = replace(
            owner,
            access_scopes=("public",),
            request_id="reduced-access-request",
        )
        identities = {
            application.react_agents.thread_id("orchestrator", context)
            for context in (owner, other_user, other_project, reduced_access)
        }

        assert len(identities) == 4
    finally:
        application.close()


def test_chat_request_generates_an_opaque_conversation_handle_and_rejects_blank_values():
    first = ChatRequest(question="What changed in RFI-087?")
    second = ChatRequest(question="What changed in RFI-087?")

    assert first.conversation_id
    assert first.conversation_id != second.conversation_id
    with pytest.raises(ValueError, match="conversation_id"):
        ChatRequest(question="What changed in RFI-087?", conversation_id="   ")


def test_owned_api_lifespan_closes_its_checkpoint_resource(monkeypatch):
    from civil_copilot.api import main as api_main

    application = build_application_runtime(corpus=generate_demo_project(seed=800))
    monkeypatch.setattr(api_main, "build_application", lambda: application)

    with TestClient(api_main.create_app()) as client:
        assert client.get("/health").status_code == 200
        assert application.checkpoints.closed is False

    assert application.checkpoints.closed is True


def test_api_returns_the_same_opaque_conversation_handle_for_the_next_turn():
    application = build_application_runtime(corpus=generate_demo_project(seed=800))
    try:
        with TestClient(create_app(application_runtime=application)) as client:
            response = client.post(
                "/api/chat",
                json={
                    "question": "What did RFI-087 decide?",
                    "conversation_id": "review-session-087",
                },
            )

        assert response.status_code == 200
        assert response.json()["conversation_id"] == "review-session-087"
    finally:
        application.close()
