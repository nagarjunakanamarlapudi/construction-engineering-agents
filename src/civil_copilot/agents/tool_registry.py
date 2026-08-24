"""Single source of truth for every model-callable project tool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from civil_copilot.agents.tool_contracts import (
    AssessStandardEvidenceInput,
    CalculateInput,
    CompareRevisionsInput,
    GetRecordInput,
    GraphQueryInput,
    ScheduleAnalysisInput,
    SearchDocumentsInput,
)
from civil_copilot.agents.tools import (
    analyze_schedule,
    assess_standard_evidence,
    calculate,
    compare_revisions,
    get_record,
    query_project_graph,
    search_documents,
)

Specialist = Literal["document", "schedule", "risk"]
AgentRole = Literal["orchestrator", "document", "schedule", "risk"]


@dataclass(frozen=True)
class ToolSpecification:
    tool: BaseTool
    description: str
    input_schema: type[BaseModel]
    acl_policy: str
    time_budget_seconds: float
    owning_specialist: Specialist
    allowed_agents: tuple[AgentRole, ...]
    read_only: bool = True

    @property
    def name(self) -> str:
        return self.tool.name


class ToolMetadata(BaseModel):
    """Serializable registry view shared by traces, UI presenters, and evaluations."""

    name: str
    description: str
    input_schema: dict[str, Any]
    acl_policy: str
    time_budget_seconds: float
    owning_specialist: Specialist
    allowed_agents: tuple[AgentRole, ...]
    read_only: bool


class ToolRegistry:
    def __init__(self, specifications: list[ToolSpecification]) -> None:
        self._specifications: dict[str, ToolSpecification] = {}
        for specification in specifications:
            if specification.name in self._specifications:
                raise ValueError(f"duplicate tool name: {specification.name}")
            if specification.input_schema is not specification.tool.args_schema:
                raise ValueError(f"tool schema mismatch: {specification.name}")
            if specification.description != specification.tool.description:
                raise ValueError(f"tool description mismatch: {specification.name}")
            self._specifications[specification.name] = specification

    def names(self) -> tuple[str, ...]:
        return tuple(self._specifications)

    def get(self, name: str) -> ToolSpecification:
        try:
            return self._specifications[name]
        except KeyError as error:
            raise KeyError(f"unknown registered tool: {name}") from error

    def tools_for(self, role: AgentRole) -> list[BaseTool]:
        return [
            specification.tool
            for specification in self._specifications.values()
            if role in specification.allowed_agents
        ]

    def metadata(self, name: str) -> ToolMetadata:
        specification = self.get(name)
        return ToolMetadata(
            name=specification.name,
            description=specification.description,
            input_schema=specification.input_schema.model_json_schema(),
            acl_policy=specification.acl_policy,
            time_budget_seconds=specification.time_budget_seconds,
            owning_specialist=specification.owning_specialist,
            allowed_agents=specification.allowed_agents,
            read_only=specification.read_only,
        )

    def metadata_for(self, role: AgentRole) -> list[ToolMetadata]:
        return [
            self.metadata(specification.name)
            for specification in self._specifications.values()
            if role in specification.allowed_agents
        ]


def _spec(
    tool_instance: BaseTool,
    schema: type[BaseModel],
    acl_policy: str,
    seconds: float,
    owner: Specialist,
    allowed_agents: tuple[AgentRole, ...],
) -> ToolSpecification:
    return ToolSpecification(
        tool=tool_instance,
        description=tool_instance.description,
        input_schema=schema,
        acl_policy=acl_policy,
        time_budget_seconds=seconds,
        owning_specialist=owner,
        allowed_agents=allowed_agents,
    )


DEFAULT_TOOL_REGISTRY = ToolRegistry(
    [
        _spec(
            search_documents,
            SearchDocumentsInput,
            "document:read",
            16.0,
            "document",
            ("orchestrator", "document", "risk"),
        ),
        _spec(
            get_record,
            GetRecordInput,
            "record:read",
            9.0,
            "document",
            ("orchestrator", "document", "schedule", "risk"),
        ),
        _spec(
            query_project_graph,
            GraphQueryInput,
            "graph:read",
            26.0,
            "risk",
            ("orchestrator", "schedule", "risk"),
        ),
        _spec(
            analyze_schedule,
            ScheduleAnalysisInput,
            "schedule:read",
            12.0,
            "schedule",
            ("orchestrator", "schedule", "risk"),
        ),
        _spec(
            compare_revisions,
            CompareRevisionsInput,
            "revision:read",
            10.0,
            "document",
            ("orchestrator", "document"),
        ),
        _spec(
            calculate,
            CalculateInput,
            "calculation:execute",
            1.0,
            "schedule",
            ("orchestrator", "schedule", "risk"),
        ),
        _spec(
            assess_standard_evidence,
            AssessStandardEvidenceInput,
            "standards:read",
            9.0,
            "document",
            ("orchestrator", "document", "risk"),
        ),
    ]
)
