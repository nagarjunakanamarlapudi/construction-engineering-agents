import os

import pytest

from civil_copilot.config import Settings
from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.evidence import HybridCandidate
from civil_copilot.runtime import RuntimeMode, build_application_reranker

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_RERANKER_SMOKE") != "1",
    reason="set RUN_RERANKER_SMOKE=1 to use the configured OpenAI reranker",
)
def test_configured_openai_reranker_returns_only_supplied_candidate_ids() -> None:
    settings = Settings()
    if settings.openai_api_key is None:
        pytest.fail("RUN_RERANKER_SMOKE=1 requires OPENAI_API_KEY")
    candidates = [
        HybridCandidate(
            chunk=DocumentChunk(
                chunk_id=chunk_id,
                record_id=record_id,
                project_id="BLR-STEEL-DEMO",
                text=text,
                ordinal=0,
                data_origin="synthetic_academic_demo",
                source_path=f"smoke/{record_id}.json",
                access_scopes=["project:blr-steel-demo"],
            ),
            fused_score=fused_score,
            text_rank=rank,
            dense_rank=rank,
        )
        for rank, (chunk_id, record_id, text, fused_score) in enumerate(
            (
                ("rfi", "RFI-087", "The approved RFI changes connection plate PL-17B.", 0.03),
                ("weather", "DAILY-001", "The daily weather was clear and dry.", 0.04),
            ),
            start=1,
        )
    ]

    outcome = build_application_reranker(
        mode=RuntimeMode.LIVE,
        settings=settings,
    ).rerank("Which passage explains the approved connection change?", candidates)

    assert outcome.trace.status == "success"
    assert outcome.trace.provider == "openai"
    assert {item.chunk.chunk_id for item in outcome.evidence} == {"rfi", "weather"}
    assert outcome.evidence[0].chunk.chunk_id == "rfi"
