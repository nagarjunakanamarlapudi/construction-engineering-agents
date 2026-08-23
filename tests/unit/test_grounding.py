from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.answer import GroundedAnswerService
from civil_copilot.retrieval.evidence import EvidenceItem, EvidencePacket, RetrievalTrace


def _packet(with_evidence: bool = True) -> EvidencePacket:
    evidence = []
    if with_evidence:
        evidence = [
            EvidenceItem(
                chunk=DocumentChunk(
                    chunk_id="RFI-087-chunk-0001",
                    record_id="RFI-087",
                    project_id="BLR-STEEL-DEMO",
                    text="RFI-087 required plate PL-17B and was incorporated in S-204 Rev 5.",
                    ordinal=0,
                    data_origin="synthetic_academic_demo",
                    source_path="data/demo#RFI-087",
                    access_scopes=["project:blr-steel-demo"],
                    metadata={"status": "closed"},
                ),
                fused_score=1.0,
                rerank_score=2.0,
                exact_id_match=True,
                reasons=["exact record identifier"],
            )
        ]
    return EvidencePacket(
        question="What did RFI-087 decide?",
        evidence=evidence,
        retrieval_trace=RetrievalTrace(),
    )


def test_grounded_fallback_answer_has_clickable_citation_for_every_evidence_statement():
    result = GroundedAnswerService().answer(_packet())

    assert result.grounded is True
    assert result.abstained is False
    assert result.citations[0].record_id == "RFI-087"
    assert "[RFI-087]" in result.answer
    assert "http://127.0.0.1:8001/api/records/RFI-087" in result.answer
    assert result.unsupported_claims == []


def test_answer_abstains_when_retrieval_has_no_evidence():
    result = GroundedAnswerService().answer(_packet(with_evidence=False))

    assert result.abstained is True
    assert result.grounded is True
    assert result.citations == []
    assert "enough evidence" in result.answer.lower()


def test_answer_style_can_bound_the_number_of_grounded_statements():
    packet = _packet()
    second_chunk = packet.evidence[0].chunk.model_copy(
        update={
            "chunk_id": "RFI-088-chunk-0001",
            "record_id": "RFI-088",
            "text": "RFI-088 confirmed the secondary framing connection.",
            "source_path": "data/demo#RFI-088",
        }
    )
    packet.evidence.append(packet.evidence[0].model_copy(update={"chunk": second_chunk}))

    result = GroundedAnswerService().answer(packet, max_statements=1)

    assert [citation.record_id for citation in result.citations] == ["RFI-087"]
