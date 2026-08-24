import importlib
import json
from decimal import Decimal

import pytest
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from civil_copilot.data.synthetic import generate_demo_project


def _module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        pytest.fail(f"required Task 2 module is missing: {error.name}")


def test_registry_exposes_seven_real_typed_read_only_langchain_tools():
    registry_module = _module("civil_copilot.agents.tool_registry")
    registry = registry_module.DEFAULT_TOOL_REGISTRY

    expected = {
        "search_documents": ("document", "document:read"),
        "get_record": ("document", "record:read"),
        "query_project_graph": ("risk", "graph:read"),
        "analyze_schedule": ("schedule", "schedule:read"),
        "compare_revisions": ("document", "revision:read"),
        "calculate": ("schedule", "calculation:execute"),
        "assess_standard_evidence": ("document", "standards:read"),
    }

    assert set(registry.names()) == set(expected)
    for name, (owner, acl_policy) in expected.items():
        specification = registry.get(name)
        assert isinstance(specification.tool, BaseTool)
        assert specification.tool.name == name
        assert specification.input_schema is specification.tool.args_schema
        assert specification.owning_specialist == owner
        assert specification.acl_policy == acl_policy
        assert specification.read_only is True
        assert specification.time_budget_seconds > 0
        assert specification.description == specification.tool.description

        properties = specification.tool.get_input_schema().model_json_schema()["properties"]
        assert "runtime" not in properties
        assert "user_id" not in properties
        assert "project_id" not in properties
        assert "access_scopes" not in properties

    metadata = {item.name: item for item in registry.metadata_for("orchestrator")}
    assert set(metadata) == set(expected)
    assert metadata["analyze_schedule"].owning_specialist == "schedule"
    assert metadata["analyze_schedule"].input_schema["properties"]["activity_ids"]
    standards = registry.get("assess_standard_evidence")
    assert standards.allowed_agents == ("orchestrator", "document", "risk")
    assert standards.input_schema.model_json_schema()["properties"]["standard"]["const"] == (
        "IS 800:2007"
    )


def test_tool_inputs_reject_unbounded_or_ambiguous_requests():
    contracts = _module("civil_copilot.agents.tool_contracts")

    with pytest.raises(ValidationError):
        contracts.SearchDocumentsInput(query="steel", top_k=21)
    with pytest.raises(ValidationError):
        contracts.GraphQueryInput(start_id="RFI-087", max_depth=6)
    with pytest.raises(ValidationError):
        contracts.ScheduleAnalysisInput(activity_ids=[])
    with pytest.raises(ValidationError):
        contracts.CompareRevisionsInput(
            document_id="S-204",
            from_revision="5",
            to_revision="5",
        )


def test_model_friendly_project_terms_normalize_to_canonical_tool_values():
    contracts = _module("civil_copilot.agents.tool_contracts")

    record = contracts.GetRecordInput(
        record_type="activity",
        record_id="ACT-STEEL-009",
    )
    graph = contracts.GraphQueryInput(
        start_id="ACT-STEEL-009",
        relationship_types=[
            "related_to",
            "blocked_by",
            "blocks",
            "referenced_by",
            "references",
        ],
        max_depth=2,
        direction="both",
    )

    assert record.record_type == "schedule_activity"
    assert graph.relationship_types == ["AFFECTS", "REFERENCES"]

    record_schema = contracts.GetRecordInput.model_json_schema()
    relationship_schema = contracts.GraphQueryInput.model_json_schema()
    assert "schedule_activity" in json.dumps(record_schema)
    assert "AFFECTS" in json.dumps(relationship_schema)


def test_calculator_accepts_bounded_arithmetic_and_rejects_code_execution():
    calculation = _module("civil_copilot.calculation.service")
    service = calculation.CalculationService()

    result = service.calculate("2 * (3 + 4)")

    assert result.value == Decimal("14")
    assert result.expression == "2 * (3 + 4)"
    with pytest.raises(ValueError, match="unsupported"):
        service.calculate("__import__('os').getcwd()")


def test_schedule_analysis_is_deterministic_and_marks_critical_activity_impact():
    schedule = _module("civil_copilot.schedule.service")
    corpus = generate_demo_project(seed=800)
    service = schedule.ScheduleImpactService(corpus.records)

    result = service.analyze(["ACT-STEEL-009"], delay_days=5)

    assert result.activity_ids == ["ACT-STEEL-009"]
    assert result.delay_days == 5
    assert result.critical_activity_ids == ["ACT-STEEL-009"]
    assert result.projected_critical_delay_days == 5
    assert result.source_ids == ["ACT-STEEL-009"]
