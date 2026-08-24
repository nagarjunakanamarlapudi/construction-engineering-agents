"""Transparent routing rules for direct RAG, Graph RAG, and multi-step investigation."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from langchain_openai import ChatOpenAI

from civil_copilot.agents.state import ChatRequest, PlanStep, RoutePlan
from civil_copilot.agents.tools import ALLOWED_TOOLS

TOOL_PURPOSES = {
    "search_documents": "Find and rerank relevant passages.",
    "get_records": "Open the records found on the project paths.",
    "find_graph_paths": "Follow verified project relationships.",
    "compare_revisions": "Compare controlled drawing revisions.",
    "get_schedule_activity": "Read the named schedule activity.",
    "query_quality_records": "Find the relevant inspection and NCR records.",
}
ANSWER_PSEUDO_STEPS = {"answer", "llm", "respond"}


class QuestionRouter:
    def route(self, request: ChatRequest) -> RoutePlan:
        question = request.question.lower()
        if request.route_override:
            route = request.route_override
            reason = "The user selected this demonstration route."
        elif "is 800" in question and any(
            term in question for term in ("compare", "evidenced", "needs review", "practices")
        ):
            route = "agentic_rag"
            reason = (
                "The question compares project evidence with an indexed official public preview."
            )
        elif any(term in question for term in ("why ", "what changed", "remain open", "closes")):
            route = "agentic_rag"
            reason = "The question combines causes, changes, or closure evidence."
        elif any(
            term in question for term in ("downstream", "trace ", "depends", "path", "impact")
        ):
            route = "graph_rag"
            reason = "The question asks for relationships or a dependency path."
        else:
            route = "rag"
            reason = "One focused evidence retrieval should answer the question."

        if route == "rag":
            steps = [
                PlanStep(
                    number=1,
                    purpose="Find the most relevant passages.",
                    tool_name="search_documents",
                )
            ]
        elif route == "graph_rag":
            steps = [
                PlanStep(
                    number=1, purpose="Follow project relationships.", tool_name="find_graph_paths"
                ),
                PlanStep(
                    number=2, purpose="Open the records on those paths.", tool_name="get_records"
                ),
            ]
        elif "quality" in question or "ncr" in question or "inspection" in question:
            steps = [
                PlanStep(
                    number=1,
                    purpose="Find the relevant quality records.",
                    tool_name="query_quality_records",
                ),
                PlanStep(
                    number=2,
                    purpose="Follow inspection and closure links.",
                    tool_name="find_graph_paths",
                ),
                PlanStep(number=3, purpose="Open the supporting records.", tool_name="get_records"),
            ]
        else:
            steps = [
                PlanStep(
                    number=1,
                    purpose="Read the schedule activity.",
                    tool_name="get_schedule_activity",
                ),
                PlanStep(
                    number=2,
                    purpose="Follow causes and affected records.",
                    tool_name="find_graph_paths",
                ),
                PlanStep(
                    number=3,
                    purpose="Compare referenced drawing revisions.",
                    tool_name="compare_revisions",
                ),
                PlanStep(
                    number=4,
                    purpose="Retrieve additional evidence if needed.",
                    tool_name="search_documents",
                ),
            ]
        return RoutePlan(route=route, reason=reason, steps=steps[: request.max_steps])


class LLMQuestionRouter:
    """Let the configured reasoning model plan, then validate against a strict tool allowlist."""

    def __init__(
        self,
        planner: Callable[[ChatRequest], Any],
        fallback: QuestionRouter | None = None,
    ) -> None:
        self.planner = planner
        self.fallback = fallback or QuestionRouter()

    @classmethod
    def from_openai(cls, api_key: str, model: str) -> LLMQuestionRouter:
        llm = ChatOpenAI(model=model, api_key=api_key, reasoning_effort="low")
        structured = llm.with_structured_output(RoutePlan, method="json_schema")

        def invoke(request: ChatRequest) -> Any:
            return structured.invoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "Route a civil-engineering project question. Use rag for one focused "
                            "retrieval, graph_rag for explicit dependency paths, and agentic_rag "
                            "for compound investigations. Direct rag must use only "
                            "search_documents. Graph rag uses find_graph_paths followed by "
                            "get_records. Use get_schedule_activity only when a named ACT record "
                            "is present; compare_revisions for drawing/revision questions; and "
                            "query_quality_records only for inspections, weld quality, or NCRs. "
                            "Produce a brief plan summary and never expose hidden "
                            "chain-of-thought. Do not add an answer, respond, or llm step; the "
                            "application assembles the final answer after the tools finish. "
                            "Allowed read-only tools: " + ", ".join(sorted(ALLOWED_TOOLS)) + "."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {request.question}\nMaximum steps: {request.max_steps}\n"
                            f"Explicit route override: {request.route_override or 'none'}"
                        ),
                    },
                ]
            )

        return cls(invoke)

    @staticmethod
    def _step(tool_name: str, number: int) -> PlanStep:
        return PlanStep(
            number=number,
            purpose=TOOL_PURPOSES[tool_name],
            tool_name=tool_name,
        )

    def _canonicalize(self, plan: RoutePlan, request: ChatRequest) -> RoutePlan:
        """Keep model routing judgment while enforcing small, explainable tool sets."""
        if plan.route == "rag":
            tools = ["search_documents"]
        elif plan.route == "graph_rag":
            tools = ["find_graph_paths", "get_records"]
        else:
            question = request.question.lower()
            has_activity = bool(re.search(r"\bact-[a-z0-9-]+\b", question))
            has_quality = any(term in question for term in ("ncr", "inspection", "weld", "quality"))
            has_revision = bool(re.search(r"\bs-\d+\b", question)) or any(
                term in question for term in ("drawing", "revision", "what changed")
            )
            needs_revision_impact = has_revision and any(
                term in question for term in ("activity", "affected", "impact", "why")
            )
            has_identifier = bool(re.search(r"\b[a-z]{2,}(?:-[a-z0-9]+)+\b", question))
            eligible = {
                "search_documents",
                "get_records",
                "find_graph_paths",
                *(["get_schedule_activity"] if has_activity else []),
                *(["query_quality_records"] if has_quality else []),
                *(["compare_revisions"] if has_revision else []),
            }
            tools = []
            for step in plan.steps:
                if step.tool_name in eligible and step.tool_name not in tools:
                    tools.append(step.tool_name)
            required: list[str] = []
            if has_quality:
                required.append("query_quality_records")
            if has_activity:
                required.append("get_schedule_activity")
            if has_revision:
                required.append("compare_revisions")
            if has_identifier or needs_revision_impact:
                required.append("find_graph_paths")
            if needs_revision_impact:
                required.append("get_records")
            for tool_name in required:
                if tool_name not in tools:
                    tools.append(tool_name)
            if not tools:
                tools = ["search_documents"]
            if has_quality:
                tools = [
                    "query_quality_records",
                    *(["get_schedule_activity"] if has_activity else []),
                    *(["compare_revisions"] if has_revision else []),
                    "find_graph_paths",
                    "get_records",
                ]
            priority = [
                "query_quality_records",
                "get_schedule_activity",
                "compare_revisions",
                "find_graph_paths",
                "get_records",
                "search_documents",
            ]
            tools.sort(key=priority.index)
        tools = tools[: request.max_steps]
        return plan.model_copy(
            update={
                "steps": [self._step(tool_name, index) for index, tool_name in enumerate(tools, 1)],
                "planner": "llm",
            }
        )

    def route(self, request: ChatRequest) -> RoutePlan:
        try:
            plan = RoutePlan.model_validate(self.planner(request))
            plan = plan.model_copy(
                update={
                    "steps": [
                        step
                        for step in plan.steps
                        if step.tool_name.lower() not in ANSWER_PSEUDO_STEPS
                    ]
                }
            )
            if request.route_override and plan.route != request.route_override:
                raise ValueError("planner ignored explicit route override")
            if not plan.steps or len(plan.steps) > request.max_steps:
                raise ValueError("planner returned an invalid step count")
            if any(step.tool_name not in ALLOWED_TOOLS for step in plan.steps):
                raise ValueError("planner selected a tool outside the allowlist")
            expected_plan = self.fallback.route(request)
            if plan.route != expected_plan.route:
                plan = plan.model_copy(
                    update={
                        "route": expected_plan.route,
                        "reason": (
                            f"The model proposed {plan.route}; the route guardrail selected "
                            f"{expected_plan.route} because {expected_plan.reason.lower()}"
                        ),
                    }
                )
            return self._canonicalize(plan, request)
        except Exception:
            return self.fallback.route(request)
