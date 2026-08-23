"""Run the versioned gold scenarios through the same workflow used by the API."""

from __future__ import annotations

import json
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.data.models import GoldScenario
from civil_copilot.data.synthetic import default_gold_scenarios
from civil_copilot.evals.metrics import (
    abstention_accuracy,
    citation_coverage,
    recall_at_k,
    reciprocal_rank,
    route_accuracy,
    tool_selection_precision,
    unnecessary_step_rate,
)


class ScenarioResult(BaseModel):
    scenario_id: str
    route: str
    expected_route: str
    retrieved_ids: list[str]
    tool_names: list[str]
    recall_at_6: float
    reciprocal_rank: float
    citation_coverage: float
    route_accuracy: float
    tool_selection_precision: float
    unnecessary_step_rate: float
    abstention_accuracy: float
    passed: bool


class EvaluationReport(BaseModel):
    schema_version: str = "1.0"
    generated_at: str
    scenario_count: int
    aggregate: dict[str, float]
    scenarios: list[ScenarioResult] = Field(default_factory=list)


class EvaluationRunner:
    def __init__(self, workflow: CopilotWorkflow) -> None:
        self.workflow = workflow

    def run(self, scenarios: list[GoldScenario]) -> EvaluationReport:
        results: list[ScenarioResult] = []
        for scenario in scenarios:
            response = self.workflow.invoke(ChatRequest(question=scenario.question))
            retrieved_ids = list(dict.fromkeys(item.chunk.record_id for item in response.evidence))
            tool_names = [event.title for event in response.trace if event.stage == "tool"]
            relevant = set(scenario.expected_evidence_ids)
            result = ScenarioResult(
                scenario_id=scenario.scenario_id,
                route=response.route,
                expected_route=scenario.expected_route,
                retrieved_ids=retrieved_ids,
                tool_names=tool_names,
                recall_at_6=recall_at_k(retrieved_ids, relevant, 6),
                reciprocal_rank=reciprocal_rank(retrieved_ids, relevant),
                citation_coverage=citation_coverage(
                    material_claims=max(len(response.citations), 1),
                    cited_claims=len(response.citations) if response.grounded else 0,
                ),
                route_accuracy=route_accuracy(response.route, scenario.expected_route),
                tool_selection_precision=tool_selection_precision(
                    tool_names, set(scenario.expected_tools)
                ),
                unnecessary_step_rate=unnecessary_step_rate(
                    len(tool_names), len(scenario.expected_tools)
                ),
                abstention_accuracy=abstention_accuracy(False, response.abstained),
                passed=(
                    response.grounded
                    and not response.abstained
                    and response.route == scenario.expected_route
                    and bool(set(retrieved_ids) & relevant)
                ),
            )
            results.append(result)

        metric_names = (
            "recall_at_6",
            "reciprocal_rank",
            "citation_coverage",
            "route_accuracy",
            "tool_selection_precision",
            "unnecessary_step_rate",
            "abstention_accuracy",
        )
        aggregate = {
            name: sum(getattr(result, name) for result in results) / max(len(results), 1)
            for name in metric_names
        }
        aggregate["scenario_pass_rate"] = sum(result.passed for result in results) / max(
            len(results), 1
        )
        return EvaluationReport(
            generated_at=datetime.now(UTC).isoformat(),
            scenario_count=len(results),
            aggregate=aggregate,
            scenarios=results,
        )


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Evaluate the versioned Civil Copilot scenarios")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use configured OpenAI/Qdrant/Langfuse services instead of the portable baseline",
    )
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    if arguments.live:
        from civil_copilot.api.main import build_workflow

        workflow = build_workflow()
        filename = "report-live.json"
    else:
        from civil_copilot.data.loaders import load_corpus
        from civil_copilot.demo import build_offline_workflow

        workflow = build_offline_workflow(load_corpus(root))
        filename = "report.json"
    report = EvaluationRunner(workflow).run(default_gold_scenarios())
    output = root / "data" / "evals" / filename
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.aggregate, indent=2, sort_keys=True))
    return 0 if report.aggregate["scenario_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
