from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from civil_copilot.agents.tool_contracts import ReadOnlyToolObservation
from civil_copilot.agents.tool_registry import DEFAULT_TOOL_REGISTRY, AgentRole
from civil_copilot.deterministic_model import DeterministicToolCallingModel


def _tool_sequence(role: AgentRole, question: str) -> tuple[list[str], frozenset[str]]:
    model = DeterministicToolCallingModel().bind_tools(DEFAULT_TOOL_REGISTRY.tools_for(role))
    allowed = frozenset(tool.name for tool in DEFAULT_TOOL_REGISTRY.tools_for(role))
    messages = [HumanMessage(content=question)]
    names: list[str] = []
    for turn in range(1, 8):
        response = model.invoke(messages)
        assert isinstance(response, AIMessage)
        if not response.tool_calls:
            break
        assert len(response.tool_calls) == 1
        call = response.tool_calls[0]
        names.append(call["name"])
        assert call["name"] in allowed
        messages.extend(
            (
                response,
                ToolMessage(
                    name=call["name"],
                    tool_call_id=call["id"],
                    content=ReadOnlyToolObservation(
                        tool_name=call["name"],
                        status="ok",
                        summary=f"Observed {call['name']} on turn {turn}.",
                        source_ids=["ACT-STEEL-009", "RFI-087", "DRAW-S-204-R5"],
                        data={"projected_critical_delay_days": 5},
                    ).model_dump_json(),
                ),
            )
        )
    else:
        raise AssertionError("portable model did not stop within its bounded teaching sequence")
    return names, allowed


def test_bound_portable_model_uses_only_document_specialist_tools():
    names, allowed = _tool_sequence(
        "document",
        "What changed between S-204 Rev 3 and Rev 5, and why?",
    )

    assert names == ["compare_revisions", "search_documents"]
    assert set(names) <= allowed


def test_bound_portable_model_uses_observed_schedule_evidence_before_graph():
    names, allowed = _tool_sequence(
        "schedule",
        "Why is ACT-STEEL-009 delayed and which milestone is affected?",
    )

    assert names == ["get_record", "analyze_schedule", "query_project_graph"]
    assert set(names) <= allowed


def test_bound_portable_model_keeps_calculation_in_the_schedule_role():
    names, allowed = _tool_sequence(
        "schedule",
        "Calculate the schedule delay for ACT-STEEL-009 using 2 + 2.",
    )

    assert names == ["calculate"]
    assert set(names) <= allowed


def test_bound_portable_model_uses_one_bounded_standards_review_action():
    names, allowed = _tool_sequence(
        "document",
        "Compare this project's structural-steel practices with the indexed IS 800 preview.",
    )

    assert names == ["assess_standard_evidence"]
    assert set(names) <= allowed


def test_specialist_scenarios_cover_all_registered_tools_without_one_mega_agent():
    document, _ = _tool_sequence(
        "document",
        "What changed between S-204 Rev 3 and Rev 5, and why?",
    )
    schedule, _ = _tool_sequence(
        "schedule",
        "Why is ACT-STEEL-009 delayed and which milestone is affected?",
    )
    calculation, _ = _tool_sequence(
        "schedule",
        "Calculate the schedule delay for ACT-STEEL-009 using 2 + 2.",
    )
    standards, _ = _tool_sequence(
        "document",
        "Compare this project's structural-steel practices with the indexed IS 800 preview.",
    )

    assert set(document + schedule + calculation + standards) == set(DEFAULT_TOOL_REGISTRY.names())
