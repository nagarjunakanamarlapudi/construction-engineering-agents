import pytest

from civil_copilot.agents.state import ChatResponse, TraceEvent
from civil_copilot.data.models import DocumentChunk, GoldScenario
from civil_copilot.evals.runner import EvaluationRunner
from civil_copilot.retrieval.answer import Citation
from civil_copilot.retrieval.evidence import (
    EvidenceItem,
    EvidencePacket,
    RerankerScoreTrace,
    RerankerTrace,
    RetrievalTrace,
)


def _evidence(record_id: str, score: float) -> EvidenceItem:
    return EvidenceItem(
        chunk=DocumentChunk(
            chunk_id=f"{record_id}-chunk",
            record_id=record_id,
            project_id="BLR-STEEL-DEMO",
            text=f"Evidence for {record_id}",
            ordinal=0,
            data_origin="synthetic_academic_demo",
            source_path=f"data/{record_id}.json",
            access_scopes=["project:blr-steel-demo"],
        ),
        fused_score=0.1,
        rerank_score=score,
    )


def test_evaluation_runner_reports_paired_hybrid_vs_reranked_ndcg_lift() -> None:
    evidence = [_evidence("B", 0.9), _evidence("A", 0.2)]
    packet = EvidencePacket(
        question="Find B",
        evidence=evidence,
        retrieval_trace=RetrievalTrace(
            fused_candidates=2,
            returned_evidence=2,
            hybrid_ranking=["A", "B"],
            reranked_ranking=["B", "A"],
            reranker=RerankerTrace(
                provider="openai",
                model="gpt-test-reranker",
                version="test-v1",
                status="success",
                failure_policy="fail_closed",
                candidate_count=2,
                scores=[
                    RerankerScoreTrace(candidate_id="B-chunk", score=0.9),
                    RerankerScoreTrace(candidate_id="A-chunk", score=0.2),
                ],
            ),
        ),
    )

    class Retriever:
        def retrieve(self, _context: object) -> EvidencePacket:
            return packet

    class Tools:
        retriever = Retriever()

    class Workflow:
        tools = Tools()

        def invoke(self, request: object) -> ChatResponse:
            return ChatResponse(
                question="Find B",
                conversation_id="eval",
                route="rag",
                answer="Evidence for B",
                grounded=True,
                abstained=False,
                citations=[
                    Citation(
                        record_id="B",
                        chunk_id="B-chunk",
                        title="B",
                        source_path="data/B.json",
                        data_origin="synthetic_academic_demo",
                    )
                ],
                trace=[
                    TraceEvent(
                        stage="tool",
                        title="search_documents",
                        summary="searched",
                    )
                ],
                evidence=evidence,
            )

    scenario = GoldScenario(
        scenario_id="reranker-lift",
        question="Find B",
        expected_route="rag",
        expected_evidence_ids=["B"],
        expected_tools=["search_documents"],
    )

    report = EvaluationRunner(Workflow()).run([scenario])  # type: ignore[arg-type]
    result = report.scenarios[0]

    assert result.ndcg_at_6 == 1.0
    assert result.hybrid_ndcg_at_6 == pytest.approx(0.6309297536)
    assert result.reranked_ndcg_at_6 == 1.0
    assert result.reranker_lift_at_6 == pytest.approx(0.3690702464)
    assert result.reranker_provider == "openai"
    assert result.reranker_model == "gpt-test-reranker"
    assert result.reranker_version == "test-v1"
    assert result.reranker_status == "success"
    assert report.aggregate["ndcg_at_6"] == 1.0
    assert report.aggregate["reranker_lift_at_6"] == pytest.approx(0.3690702464)
