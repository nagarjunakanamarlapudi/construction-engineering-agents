import os
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool

from civil_copilot.config import Settings
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.runtime import build_application_runtime

pytestmark = pytest.mark.integration


class CheckpointAwareModel(BaseChatModel):
    """Read a marker only from LangGraph-provided prior messages, never model state."""

    @property
    def _llm_type(self) -> str:
        return "checkpoint-aware-test-model"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        human_text = [
            str(message.content) for message in messages if isinstance(message, HumanMessage)
        ]
        latest = human_text[-1]
        if latest.startswith("Remember marker "):
            answer = "Marker accepted for this conversation."
        else:
            prior = next(
                (
                    text.removeprefix("Remember marker ")
                    for text in human_text[:-1]
                    if text.startswith("Remember marker ")
                ),
                None,
            )
            answer = f"Prior marker: {prior}" if prior else "No prior marker in this conversation."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION") != "1", reason="local PostgreSQL service required"
)
def test_postgres_checkpoint_resumes_after_runtime_restart_and_isolates_principals():
    conversation_id = f"restart-{uuid4().hex}"
    marker = f"steel-{uuid4().hex}"
    settings = Settings(
        mem0_api_key=None,
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )
    first_application = build_application_runtime(
        mode="local",
        settings=settings,
        corpus=generate_demo_project(seed=800),
        model=CheckpointAwareModel(),
        initialize_data=False,
    )
    first_context = first_application.tool_context(
        "checkpoint-owner",
        "BLR-STEEL-DEMO",
        ("project:blr-steel-demo",),
        conversation_id=conversation_id,
    )
    first_application.run_react(
        role="document",
        question=f"Remember marker {marker}",
        context=first_context,
    )
    first_application.close()
    assert first_application.checkpoints.closed is True

    second_application = build_application_runtime(
        mode="local",
        settings=settings,
        corpus=generate_demo_project(seed=800),
        model=CheckpointAwareModel(),
        initialize_data=False,
    )
    try:
        resumed = second_application.run_react(
            role="document",
            question="What marker did I give you?",
            context=second_application.tool_context(
                "checkpoint-owner",
                "BLR-STEEL-DEMO",
                ("project:blr-steel-demo",),
                conversation_id=conversation_id,
            ),
        )
        other_user = second_application.run_react(
            role="document",
            question="What marker did I give you?",
            context=second_application.tool_context(
                "different-user",
                "BLR-STEEL-DEMO",
                ("project:blr-steel-demo",),
                conversation_id=conversation_id,
            ),
        )
        other_project = second_application.run_react(
            role="document",
            question="What marker did I give you?",
            context=second_application.tool_context(
                "checkpoint-owner",
                "OTHER-PROJECT",
                ("project:other",),
                conversation_id=conversation_id,
            ),
        )

        assert resumed.answer == f"Prior marker: {marker}"
        assert other_user.answer == "No prior marker in this conversation."
        assert other_project.answer == "No prior marker in this conversation."
        assert second_application.capabilities.checkpoint_backend == "postgresql"
        assert second_application.capabilities.durable_checkpoints is True
    finally:
        second_application.close()
