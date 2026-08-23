"""Public request, response, route, and trace contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from civil_copilot.graph.service import GraphPath
from civil_copilot.retrieval.answer import Citation
from civil_copilot.retrieval.evidence import EvidenceItem

Route = Literal["rag", "graph_rag", "agentic_rag"]


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    user_id: str = "demo-user"
    project_id: str = "BLR-STEEL-DEMO"
    access_scopes: list[str] = Field(default_factory=lambda: ["project:blr-steel-demo", "public"])
    route_override: Route | None = None
    max_steps: int = Field(default=6, ge=1, le=8)


class PlanStep(BaseModel):
    number: int
    purpose: str
    tool_name: str


class RoutePlan(BaseModel):
    route: Route
    reason: str
    steps: list[PlanStep]
    planner: Literal["rules", "llm"] = "rules"

    @property
    def tool_names(self) -> list[str]:
        return [step.tool_name for step in self.steps]


class TraceEvent(BaseModel):
    stage: Literal["route", "plan", "tool", "evidence", "answer", "memory", "safety"]
    title: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    question: str
    route: Route
    answer: str
    grounded: bool
    abstained: bool
    citations: list[Citation] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    graph_paths: list[GraphPath] = Field(default_factory=list)
    applied_preferences: dict[str, str] = Field(default_factory=dict)
    evaluation: dict[str, float | bool | str] = Field(default_factory=dict)
