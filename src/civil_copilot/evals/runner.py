"""Run the versioned gold scenarios through the same workflow used by the API."""

from __future__ import annotations

import json
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.data.models import GoldScenario
from civil_copilot.data.synthetic import default_gold_scenarios
from civil_copilot.evals.metrics import (
    abstention_accuracy,
    citation_coverage,
    normalized_discounted_cumulative_gain,
    paired_reranker_ndcg,
    recall_at_k,
    reciprocal_rank,
    route_accuracy,
    tool_selection_precision,
    unnecessary_step_rate,
)
from civil_copilot.retrieval.query import QueryContext


class ScenarioResult(BaseModel):
    scenario_id: str
    route: str
    expected_route: str
    retrieved_ids: list[str]
    tool_names: list[str]
    recall_at_6: float
    reciprocal_rank: float
    ndcg_at_6: float
    hybrid_ndcg_at_6: float
    reranked_ndcg_at_6: float
    reranker_lift_at_6: float
    reranker_provider: str
    reranker_model: str
    reranker_version: str
    reranker_status: str
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
    runtime_capabilities: dict[str, Any] | None = None
    scenarios: list[ScenarioResult] = Field(default_factory=list)


class EvaluationRunner:
    def __init__(self, workflow: CopilotWorkflow, runtime_capabilities: Any = None) -> None:
        self.workflow = workflow
        self.runtime_capabilities = runtime_capabilities

    def run(self, scenarios: list[GoldScenario]) -> EvaluationReport:
        results: list[ScenarioResult] = []
        for scenario in scenarios:
            response = self.workflow.invoke(ChatRequest(question=scenario.question))
            retrieved_ids = list(dict.fromkeys(item.chunk.record_id for item in response.evidence))
            tool_names = [event.title for event in response.trace if event.stage == "tool"]
            relevant = set(scenario.expected_evidence_ids)
            relevance = {item_id: 1.0 for item_id in relevant}
            retrieval_packet = self.workflow.tools.retriever.retrieve(
                QueryContext(
                    question=scenario.question,
                    top_k=20,
                    minimum_rerank_score=0.0,
                )
            )
            retrieval_trace = retrieval_packet.retrieval_trace
            paired = paired_reranker_ndcg(
                retrieval_trace.hybrid_ranking,
                retrieval_trace.reranked_ranking,
                relevance,
                6,
            )
            reranker_trace = retrieval_trace.reranker
            result = ScenarioResult(
                scenario_id=scenario.scenario_id,
                route=response.route,
                expected_route=scenario.expected_route,
                retrieved_ids=retrieved_ids,
                tool_names=tool_names,
                recall_at_6=recall_at_k(retrieved_ids, relevant, 6),
                reciprocal_rank=reciprocal_rank(retrieved_ids, relevant),
                ndcg_at_6=normalized_discounted_cumulative_gain(retrieved_ids, relevance, 6),
                hybrid_ndcg_at_6=paired.hybrid_ndcg,
                reranked_ndcg_at_6=paired.reranked_ndcg,
                reranker_lift_at_6=paired.lift,
                reranker_provider=reranker_trace.provider if reranker_trace else "unavailable",
                reranker_model=reranker_trace.model if reranker_trace else "unavailable",
                reranker_version=reranker_trace.version if reranker_trace else "unavailable",
                reranker_status=reranker_trace.status if reranker_trace else "unavailable",
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
            "ndcg_at_6",
            "hybrid_ndcg_at_6",
            "reranked_ndcg_at_6",
            "reranker_lift_at_6",
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
            runtime_capabilities=(
                self.runtime_capabilities.model_dump(mode="json")
                if hasattr(self.runtime_capabilities, "model_dump")
                else self.runtime_capabilities
            ),
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
        from civil_copilot.config import Settings
        from civil_copilot.runtime import RuntimeMode, build_application_runtime

        application = build_application_runtime(mode=RuntimeMode.LIVE, settings=Settings())
        try:
            report = application.evaluator.run(default_gold_scenarios())
        finally:
            application.close()
        filename = "report-live.json"
    else:
        from civil_copilot.data.loaders import load_corpus
        from civil_copilot.demo import build_offline_workflow

        workflow = build_offline_workflow(load_corpus(root))
        report = EvaluationRunner(
            workflow,
            runtime_capabilities={
                "mode": "portable",
                "records_backend": "memory",
                "search_backend": "memory_bm25_and_deterministic_dense",
                "graph_backend": "networkx",
                "server_filtered": False,
                "fallback_allowed": False,
            },
        ).run(default_gold_scenarios())
        filename = "report.json"
    output = root / "data" / "evals" / filename
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.aggregate, indent=2, sort_keys=True))
    return 0 if report.aggregate["scenario_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
