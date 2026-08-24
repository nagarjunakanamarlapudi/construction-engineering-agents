"""Small, deterministic supervisor for compound-question specialist handoffs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from civil_copilot.agents.tool_registry import (
    DEFAULT_TOOL_REGISTRY,
    AgentRole,
    ToolRegistry,
)

OrchestrationMode = Literal["specialist", "orchestrator"]


class SpecialistAssignment(BaseModel):
    """One visible, bounded handoff to a compiled role-specific agent."""

    role: AgentRole
    reason: str = Field(min_length=1, max_length=300)
    matched_signals: list[str] = Field(default_factory=list, max_length=12)
    allowed_tools: list[str] = Field(min_length=1)


class SpecialistRoutingDecision(BaseModel):
    """Public, serializable explanation of the supervisor's delegation choice."""

    mode: OrchestrationMode
    reason: str = Field(min_length=1, max_length=500)
    assignments: list[SpecialistAssignment] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_assignments(self) -> SpecialistRoutingDecision:
        roles = self.roles
        if len(set(roles)) != len(roles):
            raise ValueError("specialist roles must not repeat")
        if self.mode == "orchestrator" and roles != ["orchestrator"]:
            raise ValueError("orchestrator mode must contain only the orchestrator")
        if self.mode == "specialist" and "orchestrator" in roles:
            raise ValueError("specialist mode cannot contain the general orchestrator")
        return self

    @property
    def roles(self) -> list[AgentRole]:
        return [assignment.role for assignment in self.assignments]


DOCUMENT_SIGNALS = (
    "drawing",
    "revision",
    " rev ",
    "what changed",
    "rfi",
    "submittal",
    "specification",
    "clause",
    "document",
    "standard",
    "is 800",
    "public preview",
)
SCHEDULE_SIGNALS = (
    "act-",
    "activity",
    "schedule",
    "delay",
    "delayed",
    "milestone",
    "critical path",
    "float",
    "programme",
    "program",
)
RISK_SIGNALS = (
    "risk",
    "quality",
    "ncr",
    "inspection",
    "weld",
    "nonconformance",
    "non-conformance",
    "defect",
    "unsafe",
)


class SpecialistRouter:
    """Choose the narrowest safe compiled role from transparent domain signals."""

    def __init__(self, registry: ToolRegistry = DEFAULT_TOOL_REGISTRY) -> None:
        self.registry = registry

    @staticmethod
    def _matches(question: str, signals: tuple[str, ...]) -> list[str]:
        padded = f" {question.lower()} "
        return [signal.strip() for signal in signals if signal in padded]

    def _assignment(
        self,
        role: AgentRole,
        reason: str,
        signals: list[str],
    ) -> SpecialistAssignment:
        return SpecialistAssignment(
            role=role,
            reason=reason,
            matched_signals=list(dict.fromkeys(signals)),
            allowed_tools=sorted(tool.name for tool in self.registry.tools_for(role)),
        )

    def route(
        self,
        question: str,
        *,
        max_specialists: int = 2,
    ) -> SpecialistRoutingDecision:
        if max_specialists < 1:
            raise ValueError("max_specialists must be at least one")
        document = self._matches(question, DOCUMENT_SIGNALS)
        schedule = self._matches(question, SCHEDULE_SIGNALS)
        risk = self._matches(question, RISK_SIGNALS)

        assignments: list[SpecialistAssignment] = []
        if risk:
            if document and max_specialists > 1:
                assignments.append(
                    self._assignment(
                        "document",
                        "Open the controlled document or revision evidence first.",
                        document,
                    )
                )
            assignments.append(
                self._assignment(
                    "risk",
                    "Assess and rank the evidence-backed quality or risk concern.",
                    risk,
                )
            )
        elif document and schedule and max_specialists > 1:
            assignments.extend(
                (
                    self._assignment(
                        "document",
                        "Establish what the controlled document or revision says.",
                        document,
                    ),
                    self._assignment(
                        "schedule",
                        "Assess the linked activity or milestone effect.",
                        schedule,
                    ),
                )
            )
        elif document:
            assignments.append(
                self._assignment(
                    "document",
                    "The question is primarily about controlled project documents or revisions.",
                    document,
                )
            )
        elif schedule:
            assignments.append(
                self._assignment(
                    "schedule",
                    "The question is primarily about activities, dates, or schedule impact.",
                    schedule,
                )
            )

        if assignments:
            assignments = assignments[: min(max_specialists, 2)]
            return SpecialistRoutingDecision(
                mode="specialist",
                reason=(
                    "The Copilot Orchestrator selected the smallest domain-specific "
                    "team that can investigate this compound question."
                ),
                assignments=assignments,
            )

        return SpecialistRoutingDecision(
            mode="orchestrator",
            reason=(
                "No narrow civil-engineering domain signal was strong enough, so the "
                "bounded general orchestrator remains responsible."
            ),
            assignments=[
                self._assignment(
                    "orchestrator",
                    "Handle the ambiguous compound question with the general bounded role.",
                    [],
                )
            ],
        )
