from civil_copilot.evals.metrics import (
    acl_safety,
    budget_compliance,
    latency_compliance,
    observation_replan_success,
    repetition_rate,
    tool_selection_recall,
)


def test_agent_evaluation_suite_scores_a_deterministic_or_live_run_from_one_contract():
    from civil_copilot.agents.react import ReactRunResult, ReactTraceEvent
    from civil_copilot.agents.tool_contracts import ReadOnlyToolObservation
    from civil_copilot.evals.agent import AgentEvaluationCase, evaluate_agent_run

    run = ReactRunResult(
        role="orchestrator",
        answer="Supported result.",
        tool_names=["analyze_schedule", "query_project_graph"],
        observations=[
            ReadOnlyToolObservation(
                tool_name="analyze_schedule",
                status="ok",
                summary="Critical delay found.",
                source_ids=["ACT-STEEL-009"],
            ),
            ReadOnlyToolObservation(
                tool_name="query_project_graph",
                status="ok",
                summary="Impacts found.",
                source_ids=["ACT-STEEL-009", "RFI-087"],
            ),
        ],
        source_ids=["ACT-STEEL-009", "RFI-087"],
        trace=[
            ReactTraceEvent(
                phase="plan",
                title="Plan",
                summary="Plan.",
                model_turn=0,
            ),
            ReactTraceEvent(
                phase="act",
                title="Analyze",
                summary="Analyze.",
                tool_name="analyze_schedule",
                model_turn=1,
                tool_call_id="schedule-call",
            ),
            ReactTraceEvent(
                phase="observe",
                title="Observed",
                summary="Observed.",
                tool_name="analyze_schedule",
                model_turn=1,
                tool_call_id="schedule-call",
            ),
            ReactTraceEvent(
                phase="decide",
                title="Decide",
                summary="Decide.",
                tool_name="analyze_schedule",
                model_turn=2,
            ),
            ReactTraceEvent(
                phase="act",
                title="Graph",
                summary="Graph.",
                tool_name="query_project_graph",
                model_turn=2,
                tool_call_id="graph-call",
            ),
        ],
        stop_reason="completed",
        abstained=False,
        thread_id="eval-thread",
        elapsed_ms=120,
        estimated_cost_usd=0.02,
    )
    case = AgentEvaluationCase(
        case_id="schedule-impact",
        mode="deterministic",
        expected_tools={"analyze_schedule", "query_project_graph"},
        observation_index=0,
        expected_next_tool="query_project_graph",
        required_source_ids={"ACT-STEEL-009"},
        permitted_source_ids={"ACT-STEEL-009", "RFI-087"},
        max_elapsed_ms=200,
        max_cost_usd=0.05,
    )

    evaluation = evaluate_agent_run(case, run)

    assert evaluation.passed is True
    assert evaluation.tool_metadata[0].name == "analyze_schedule"
    assert evaluation.tool_metadata[0].acl_policy == "schedule:read"
    assert evaluation.observation_driven is True
    assert evaluation.metrics == {
        "convergence": 1.0,
        "tool_selection_recall": 1.0,
        "tool_repetition_avoidance": 1.0,
        "observation_replan_success": 1.0,
        "grounding": 1.0,
        "acl_safety": 1.0,
        "latency_compliance": 1.0,
        "budget_compliance": 1.0,
    }


def test_agent_trajectory_metrics_cover_choice_replanning_acl_latency_and_cost():
    assert (
        tool_selection_recall(["analyze_schedule", "query_project_graph"], {"analyze_schedule"})
        == 1.0
    )
    assert (
        observation_replan_success(
            ["analyze_schedule", "query_project_graph"],
            observation_index=0,
            expected_next_tool="query_project_graph",
            model_turns=[1, 2],
            observed_turn=1,
        )
        == 1.0
    )
    assert (
        observation_replan_success(
            ["analyze_schedule", "query_project_graph"],
            observation_index=0,
            expected_next_tool="query_project_graph",
        )
        == 0.0
    )
    assert repetition_rate(["calculate", "calculate", "get_record"]) == 1 / 3
    assert acl_safety(denied_attempts=1, leaked_source_ids=[]) == 1.0
    assert acl_safety(denied_attempts=1, leaked_source_ids=["PRIVATE-1"]) == 0.0
    assert latency_compliance(elapsed_ms=180, budget_ms=200) == 1.0
    assert budget_compliance(actual_cost_usd=0.02, cost_budget_usd=0.05) == 1.0


def test_empty_or_zero_budget_metric_edges_are_deterministic():
    assert tool_selection_recall([], set()) == 1.0
    assert repetition_rate([]) == 0.0
    assert latency_compliance(elapsed_ms=0, budget_ms=0) == 1.0
    assert budget_compliance(actual_cost_usd=0, cost_budget_usd=0) == 1.0


def test_agent_eval_rejects_a_second_action_from_the_same_model_turn():
    from civil_copilot.agents.react import ReactRunResult, ReactTraceEvent
    from civil_copilot.evals.agent import AgentEvaluationCase, evaluate_agent_run

    run = ReactRunResult(
        role="orchestrator",
        answer="Unsafe parallel result.",
        tool_names=["analyze_schedule", "query_project_graph"],
        source_ids=["ACT-STEEL-009"],
        trace=[
            ReactTraceEvent(
                phase="act",
                title="Schedule",
                summary="Schedule.",
                tool_name="analyze_schedule",
                model_turn=1,
                tool_call_id="schedule",
            ),
            ReactTraceEvent(
                phase="act",
                title="Graph",
                summary="Graph.",
                tool_name="query_project_graph",
                model_turn=1,
                tool_call_id="graph",
            ),
            ReactTraceEvent(
                phase="observe",
                title="Observed schedule",
                summary="Observed.",
                tool_name="analyze_schedule",
                model_turn=1,
                tool_call_id="schedule",
            ),
        ],
        stop_reason="completed",
        abstained=False,
        thread_id="parallel",
    )
    case = AgentEvaluationCase(
        case_id="parallel-rejected",
        mode="deterministic",
        expected_tools={"analyze_schedule", "query_project_graph"},
        expected_next_tool="query_project_graph",
        permitted_source_ids={"ACT-STEEL-009"},
        max_elapsed_ms=100,
        max_cost_usd=0.1,
    )

    result = evaluate_agent_run(case, run)

    assert result.observation_driven is False
    assert result.metrics["observation_replan_success"] == 0.0
    assert result.passed is False


def test_agent_eval_explicitly_rejects_non_converging_repeated_tool_run():
    from civil_copilot.agents.react import ReactRunResult
    from civil_copilot.evals.agent import AgentEvaluationCase, evaluate_agent_run

    run = ReactRunResult(
        role="document",
        answer="The investigation reached its step limit without a publishable answer.",
        tool_names=["search_documents", "search_documents", "search_documents"],
        source_ids=["DRAW-S-204-R5"],
        stop_reason="step_limit",
        abstained=True,
        thread_id="non-converging-search",
    )
    case = AgentEvaluationCase(
        case_id="non-converging-search",
        mode="live",
        expected_tools={"search_documents"},
        expected_next_tool="search_documents",
        required_source_ids={"DRAW-S-204-R5"},
        permitted_source_ids={"DRAW-S-204-R5"},
        max_elapsed_ms=30_000,
        max_cost_usd=0.25,
    )

    result = evaluate_agent_run(case, run)

    assert result.metrics["convergence"] == 0.0
    assert result.metrics["tool_repetition_avoidance"] < 1.0
    assert result.passed is False


def test_agent_eval_rejects_expected_tool_when_an_intermediate_action_occurs_first():
    from civil_copilot.agents.react import ReactRunResult, ReactTraceEvent
    from civil_copilot.evals.agent import AgentEvaluationCase, evaluate_agent_run

    run = ReactRunResult(
        role="orchestrator",
        answer="Graph eventually called.",
        tool_names=["analyze_schedule", "calculate", "query_project_graph"],
        source_ids=["ACT-STEEL-009"],
        trace=[
            ReactTraceEvent(
                phase="act",
                title="Schedule",
                summary="Schedule.",
                tool_name="analyze_schedule",
                model_turn=1,
                tool_call_id="schedule",
            ),
            ReactTraceEvent(
                phase="observe",
                title="Observed schedule",
                summary="Observed.",
                tool_name="analyze_schedule",
                model_turn=1,
                tool_call_id="schedule",
            ),
            ReactTraceEvent(
                phase="decide",
                title="Decide",
                summary="Decide.",
                model_turn=2,
            ),
            ReactTraceEvent(
                phase="act",
                title="Calculate",
                summary="Calculate.",
                tool_name="calculate",
                model_turn=2,
                tool_call_id="calculate",
            ),
            ReactTraceEvent(
                phase="observe",
                title="Observed calculation",
                summary="Observed.",
                tool_name="calculate",
                model_turn=2,
                tool_call_id="calculate",
            ),
            ReactTraceEvent(
                phase="act",
                title="Graph",
                summary="Graph.",
                tool_name="query_project_graph",
                model_turn=3,
                tool_call_id="graph",
            ),
        ],
        stop_reason="completed",
        abstained=False,
        thread_id="intermediate-action",
    )
    case = AgentEvaluationCase(
        case_id="intermediate-action-rejected",
        mode="deterministic",
        expected_tools={"analyze_schedule", "query_project_graph"},
        expected_next_tool="query_project_graph",
        permitted_source_ids={"ACT-STEEL-009"},
        max_elapsed_ms=100,
        max_cost_usd=0.1,
    )

    result = evaluate_agent_run(case, run)

    assert result.observation_driven is False
    assert result.metrics["observation_replan_success"] == 0.0
    assert result.passed is False
