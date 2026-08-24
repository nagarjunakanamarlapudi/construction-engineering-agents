from __future__ import annotations

from typing import Any

import pytest

from civil_copilot.agents.state import ChatRequest
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.application_tools import StoreBackedProjectTools, StoreBackedRetriever
from civil_copilot.config import Settings
from civil_copilot.data.models import DocumentChunk
from civil_copilot.evals.metrics import paired_reranker_ndcg
from civil_copilot.retrieval.evidence import HybridCandidate
from civil_copilot.retrieval.query import QueryContext
from civil_copilot.retrieval.rerank import (
    DeterministicHeuristicReranker,
    OpenAIListwiseReranker,
    RerankerFailurePolicy,
)
from civil_copilot.runtime import RuntimeMode, build_application_reranker


def _chunk(
    chunk_id: str,
    record_id: str,
    text: str,
    *,
    scopes: list[str] | None = None,
    source_path: str | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        record_id=record_id,
        project_id="BLR-STEEL-DEMO",
        text=text,
        ordinal=0,
        data_origin="synthetic_academic_demo",
        source_path=source_path or f"data/synthetic/{record_id}.json",
        access_scopes=scopes or ["project:blr-steel-demo"],
        metadata={"status": "current"},
    )


def _candidate(
    chunk_id: str,
    record_id: str,
    text: str,
    fused_score: float,
    *,
    exact_rank: int | None = None,
    scopes: list[str] | None = None,
) -> HybridCandidate:
    return HybridCandidate(
        chunk=_chunk(chunk_id, record_id, text, scopes=scopes),
        fused_score=fused_score,
        exact_rank=exact_rank,
        text_rank=1,
        dense_rank=1,
    )


class _StructuredRunnable:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[Any] = []

    def invoke(self, request: object) -> object:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _StructuredChatModel:
    def __init__(self, response: object) -> None:
        self.runnable = _StructuredRunnable(response)
        self.schema: object | None = None

    def with_structured_output(self, schema: object, **_kwargs: object) -> _StructuredRunnable:
        self.schema = schema
        return self.runnable


def test_openai_reranker_changes_fused_order_and_preserves_exact_provenance() -> None:
    model = _StructuredChatModel(
        {
            "rankings": [
                {"candidate_id": "b", "relevance_score": 0.96, "reason": "answers why"},
                {"candidate_id": "a", "relevance_score": 0.31, "reason": "background"},
            ]
        }
    )
    candidates = [
        _candidate("a", "RFI-087", "RFI-087 general background", 0.9, exact_rank=1),
        _candidate("b", "DRAW-S-204-R5", "Approved change and its reason", 0.5),
    ]

    outcome = OpenAIListwiseReranker(
        chat_model=model,
        model_name="gpt-test-reranker",
        model_version="2026-08-01",
    ).rerank("Why did RFI-087 change S-204?", candidates)

    assert [item.chunk.chunk_id for item in outcome.evidence] == ["b", "a"]
    exact = next(item for item in outcome.evidence if item.chunk.chunk_id == "a")
    assert exact.exact_id_match is True
    assert exact.chunk.source_path == "data/synthetic/RFI-087.json"
    assert outcome.trace.provider == "openai"
    assert outcome.trace.model == "gpt-test-reranker"
    assert outcome.trace.version == "2026-08-01"
    assert outcome.trace.status == "success"
    assert [(item.candidate_id, item.score) for item in outcome.trace.scores] == [
        ("b", 0.96),
        ("a", 0.31),
    ]
    paired = paired_reranker_ndcg(
        ["RFI-087", "DRAW-S-204-R5"],
        [item.chunk.record_id for item in outcome.evidence],
        {"DRAW-S-204-R5": 1.0},
        k=2,
    )
    assert paired.lift > 0


def test_openai_reranker_ignores_unknown_ids_but_requires_all_real_candidates() -> None:
    model = _StructuredChatModel(
        {
            "rankings": [
                {"candidate_id": "invented", "relevance_score": 1.0, "reason": "not real"},
                {"candidate_id": "a", "relevance_score": 0.2, "reason": "weak"},
                {"candidate_id": "b", "relevance_score": 0.9, "reason": "strong"},
            ]
        }
    )

    outcome = OpenAIListwiseReranker(
        chat_model=model,
        model_name="gpt-test-reranker",
    ).rerank(
        "connection change",
        [
            _candidate("a", "RFI-087", "old discussion", 0.8),
            _candidate("b", "DRAW-S-204-R5", "approved connection change", 0.4),
        ],
    )

    assert [item.chunk.chunk_id for item in outcome.evidence] == ["b", "a"]
    assert "invented" not in {item.candidate_id for item in outcome.trace.scores}
    assert outcome.trace.ignored_candidate_ids == ["invented"]


@pytest.mark.parametrize(
    ("policy", "expected_status", "expected_ids"),
    [
        (RerankerFailurePolicy.FAIL_CLOSED, "failed", []),
        (RerankerFailurePolicy.HEURISTIC_FALLBACK, "fallback", ["a", "b"]),
    ],
)
def test_openai_reranker_failure_policy_is_explicit_and_never_invents_evidence(
    policy: RerankerFailurePolicy,
    expected_status: str,
    expected_ids: list[str],
) -> None:
    model = _StructuredChatModel(TimeoutError("credential-like-secret must not leak"))
    candidates = [
        _candidate("a", "RFI-087", "RFI-087 approved answer", 0.8, exact_rank=1),
        _candidate("b", "DRAW-S-204-R5", "unrelated drawing", 0.4),
    ]

    outcome = OpenAIListwiseReranker(
        chat_model=model,
        model_name="gpt-test-reranker",
        failure_policy=policy,
    ).rerank("What is RFI-087?", candidates)

    assert outcome.trace.status == expected_status
    assert [item.chunk.chunk_id for item in outcome.evidence] == expected_ids
    assert outcome.trace.error_type == "TimeoutError"
    assert "credential-like-secret" not in outcome.trace.model_dump_json()
    if policy is RerankerFailurePolicy.HEURISTIC_FALLBACK:
        assert outcome.trace.provider == "deterministic"
        assert outcome.trace.model == "exact_lexical_revision_heuristic"
        assert outcome.trace.attempted_provider == "openai"
        assert outcome.trace.attempted_model == "gpt-test-reranker"


def test_store_retriever_sends_only_acl_filtered_bounded_candidates_to_reranker() -> None:
    class UnsafeSearchReader:
        def search_hybrid(self, **_kwargs: object) -> list[HybridCandidate]:
            return [
                _candidate("visible", "RFI-087", "v" * 5000, 0.7),
                _candidate(
                    "restricted",
                    "CLAIM-001",
                    "commercial claim",
                    0.99,
                    scopes=["restricted:commercial"],
                ),
            ]

    class CapturingReranker(DeterministicHeuristicReranker):
        seen_ids: list[str]

        def __init__(self) -> None:
            self.seen_ids = []

        def rerank(self, question: str, candidates: list[HybridCandidate]):  # type: ignore[no-untyped-def]
            self.seen_ids = [candidate.chunk.chunk_id for candidate in candidates]
            return super().rerank(question, candidates)

    reranker = CapturingReranker()
    packet = StoreBackedRetriever(UnsafeSearchReader(), reranker=reranker).retrieve(
        QueryContext(
            question="What is RFI-087?",
            project_id="BLR-STEEL-DEMO",
            access_scopes=["project:blr-steel-demo"],
            top_k=4,
        )
    )

    assert reranker.seen_ids == ["visible"]
    assert [item.chunk.chunk_id for item in packet.evidence] == ["visible"]
    assert packet.retrieval_trace.reranker.candidate_count == 1


def test_openai_reranker_bounds_candidate_count_and_text_sent_to_model() -> None:
    candidates = [
        _candidate(str(index), f"REC-{index:03d}", f"candidate {index} " + "x" * 3000, 1 / index)
        for index in range(1, 26)
    ]
    model = _StructuredChatModel(
        {
            "rankings": [
                {
                    "candidate_id": str(index),
                    "relevance_score": 1 - (index / 100),
                    "reason": "bounded",
                }
                for index in range(1, 21)
            ]
        }
    )

    outcome = OpenAIListwiseReranker(
        chat_model=model,
        model_name="gpt-test-reranker",
        max_candidates=20,
        max_text_chars=1200,
    ).rerank("question", candidates)

    assert outcome.trace.candidate_count == 20
    assert outcome.trace.input_candidate_ids == [str(index) for index in range(1, 21)]
    serialized_request = str(model.runnable.requests[0])
    assert "candidate 20" in serialized_request
    assert "candidate 21" not in serialized_request
    assert "x" * 1201 not in serialized_request


def test_fast_rag_invokes_model_reranker_once_and_keeps_its_order() -> None:
    class SearchReader:
        def search_hybrid(self, **_kwargs: object) -> list[HybridCandidate]:
            return [
                _candidate("a", "RFI-087", "RFI-087 broad background", 0.9, exact_rank=1),
                _candidate("b", "DRAW-S-204-R5", "approved connection change", 0.4),
            ]

    class EmptyRecordReader:
        def query_records(self, **_kwargs: object) -> list[object]:
            return []

    class EmptyGraphReader:
        def find_paths(self, *_args: object, **_kwargs: object) -> list[object]:
            return []

    model = _StructuredChatModel(
        {
            "rankings": [
                {"candidate_id": "b", "relevance_score": 0.99, "reason": "direct answer"},
                {"candidate_id": "a", "relevance_score": 0.10, "reason": "background"},
            ]
        }
    )
    reranker = OpenAIListwiseReranker(chat_model=model, model_name="gpt-test-reranker")
    tools = StoreBackedProjectTools(
        EmptyRecordReader(),
        SearchReader(),
        EmptyGraphReader(),
        default_project_id="BLR-STEEL-DEMO",
        default_access_scopes=("project:blr-steel-demo",),
        reranker=reranker,
    )

    response = CopilotWorkflow(tools).invoke(ChatRequest(question="Summarize RFI-087"))

    assert [item.chunk.chunk_id for item in response.evidence] == ["b", "a"]
    assert len(model.runnable.requests) == 1


def test_runtime_selects_named_heuristic_only_for_portable_and_openai_for_local_live() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_reranker_model="gpt-5-mini-test",
        reranker_failure_policy="fail_closed",
        reranker_timeout_seconds=4.0,
        reranker_max_candidates=12,
        reranker_max_text_chars=900,
    )

    portable = build_application_reranker(mode=RuntimeMode.PORTABLE, settings=settings)
    local = build_application_reranker(mode=RuntimeMode.LOCAL, settings=settings)
    live = build_application_reranker(mode=RuntimeMode.LIVE, settings=settings)

    assert isinstance(portable, DeterministicHeuristicReranker)
    assert isinstance(local, OpenAIListwiseReranker)
    assert isinstance(live, OpenAIListwiseReranker)
    assert local.model_name == "gpt-5-mini-test"
    assert local.timeout_seconds == 4.0
    assert local.max_candidates == 12
    assert local.max_text_chars == 900
