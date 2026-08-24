"""Deterministic tool-calling chat model for portable regression runs."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field


class DeterministicToolCallingModel(BaseChatModel):
    """Exercise the real bounded tool loop without a network model dependency."""

    bound_tool_names: frozenset[str] = Field(default_factory=frozenset, exclude=True)

    @property
    def _llm_type(self) -> str:
        return "civil-copilot-deterministic-tool-calling"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> DeterministicToolCallingModel:
        names = frozenset(tool.name for tool in tools if isinstance(tool, BaseTool))
        return self.model_copy(update={"bound_tool_names": names})

    @staticmethod
    def _question(messages: list[BaseMessage]) -> str:
        return next(
            (str(message.content) for message in messages if isinstance(message, HumanMessage)),
            "",
        )

    @staticmethod
    def _call(name: str, arguments: dict[str, Any], call_number: int) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": name,
                                "args": arguments,
                                "id": f"portable-{call_number}-{name}",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )

    @staticmethod
    def _observations(messages: list[BaseMessage]) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
                continue
            try:
                payload = json.loads(message.content)
            except (TypeError, ValueError):
                payload = {}
            observations.append(
                {
                    "tool_name": message.name or payload.get("tool_name", ""),
                    "status": payload.get("status", "error"),
                    "source_ids": payload.get("source_ids", []),
                    "data": payload.get("data", {}),
                }
            )
        return observations

    @staticmethod
    def _revision_arguments(question: str) -> dict[str, str]:
        document = re.search(r"\bS-\d+\b", question.upper())
        revisions = re.findall(r"\bREV(?:ISION)?\s*([A-Z0-9.-]+)", question.upper())
        return {
            "document_id": document.group(0) if document else "S-204",
            "from_revision": revisions[0] if revisions else "3",
            "to_revision": revisions[1] if len(revisions) > 1 else "5",
        }

    @staticmethod
    def _calculation_expression(question: str) -> str:
        match = re.search(r"\bUSING\s+([0-9().+*/\-\s]+)", question.upper())
        return match.group(1).strip().rstrip(".") if match else "2 + 2"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        question = self._question(messages)
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        call_number = len(tool_messages) + 1
        observations = self._observations(messages)
        used = {str(observation["tool_name"]) for observation in observations}
        available = self.bound_tool_names
        upper_question = question.upper()
        activity = re.search(r"\bACT-[A-Z0-9-]+\b", upper_question)
        record = re.search(r"\b(?:RFI|NCR|DRAW|PIECE|WELD|INSP)-[A-Z0-9-]+\b", upper_question)
        observed_sources = list(
            dict.fromkeys(
                source_id
                for observation in observations
                if observation["status"] == "ok"
                for source_id in observation["source_ids"]
            )
        )
        graph_start = activity.group(0) if activity else record.group(0) if record else None
        if graph_start is None and observed_sources:
            graph_start = observed_sources[0]

        if "CALCULATE" in upper_question and "calculate" in available and "calculate" not in used:
            return self._call(
                "calculate",
                {"expression": self._calculation_expression(question)},
                call_number,
            )
        if "calculate" in used and "CALCULATE" in upper_question:
            return self._completed()

        is_standards_review = "IS 800" in upper_question and any(
            phrase in upper_question
            for phrase in ("COMPARE", "EVIDENCED", "NEEDS REVIEW", "PRACTICES")
        )
        if (
            is_standards_review
            and "assess_standard_evidence" in available
            and "assess_standard_evidence" not in used
        ):
            return self._call(
                "assess_standard_evidence",
                {"standard": "IS 800:2007"},
                call_number,
            )
        if "assess_standard_evidence" in used:
            return self._completed()

        is_revision_question = bool(
            re.search(r"\bREV(?:ISION)?\b|\bWHAT CHANGED\b", upper_question)
        )
        if (
            is_revision_question
            and "compare_revisions" in available
            and "compare_revisions" not in used
        ):
            return self._call(
                "compare_revisions",
                self._revision_arguments(question),
                call_number,
            )
        if (
            "compare_revisions" in used
            and "search_documents" in available
            and "search_documents" not in used
        ):
            return self._call(
                "search_documents",
                {"query": question, "filters": {}, "top_k": 6},
                call_number,
            )
        if "compare_revisions" in used:
            return self._completed()

        is_schedule_specialist = (
            "analyze_schedule" in available and "search_documents" not in available
        )
        if is_schedule_specialist and activity:
            if "get_record" not in used:
                return self._call(
                    "get_record",
                    {
                        "record_type": "schedule_activity",
                        "record_id": activity.group(0),
                        "as_of_date": None,
                    },
                    call_number,
                )
            if (
                observations[-1]["status"] == "ok"
                and "analyze_schedule" in available
                and "analyze_schedule" not in used
            ):
                return self._call(
                    "analyze_schedule",
                    {
                        "activity_ids": [activity.group(0)],
                        "delay_days": 5,
                        "as_of_date": None,
                    },
                    call_number,
                )
            if (
                "analyze_schedule" in used
                and observations[-1]["status"] == "ok"
                and "query_project_graph" in available
                and "query_project_graph" not in used
            ):
                return self._call(
                    "query_project_graph",
                    {
                        "start_id": activity.group(0),
                        "relationship_types": [],
                        "max_depth": 3,
                        "direction": "both",
                    },
                    call_number,
                )
            return self._completed()

        if activity:
            if "get_record" in available and "get_record" not in used:
                return self._call(
                    "get_record",
                    {
                        "record_type": "schedule_activity",
                        "record_id": activity.group(0),
                        "as_of_date": None,
                    },
                    call_number,
                )
            if "query_project_graph" in available and "query_project_graph" not in used:
                return self._call(
                    "query_project_graph",
                    {
                        "start_id": graph_start or activity.group(0),
                        "relationship_types": [],
                        "max_depth": 3,
                        "direction": "both",
                    },
                    call_number,
                )
            if "search_documents" in available and "search_documents" not in used:
                return self._call(
                    "search_documents",
                    {"query": question, "filters": {}, "top_k": 6},
                    call_number,
                )
        elif "search_documents" in available and "search_documents" not in used:
            return self._call(
                "search_documents",
                {"query": question, "filters": {}, "top_k": 6},
                call_number,
            )
        elif (
            record
            and "query_project_graph" in available
            and "query_project_graph" not in used
            and bool(observed_sources)
        ):
            return self._call(
                "query_project_graph",
                {
                    "start_id": record.group(0),
                    "relationship_types": [],
                    "max_depth": 3,
                    "direction": "both",
                },
                call_number,
            )

        return self._completed()

    @staticmethod
    def _completed() -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Completed the bounded investigation from permitted sources."
                    )
                )
            ]
        )
