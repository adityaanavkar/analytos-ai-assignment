"""Focused tests for deterministic evidence sufficiency behavior."""

from app.rag.evidence import DeterministicEvidenceGate
from app.rag.models import RetrievedChunk


def _chunk(content: str, chunk_id: str = "chunk") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        content=content,
        title="Policy",
        source_path="KnowledgeBase/Finance/Policy.pdf",
    )


def test_gate_accepts_supported_two_term_question() -> None:
    result = DeterministicEvidenceGate().assess(
        "What is the reimbursement timeline?",
        [_chunk("Reimbursement is processed within 7 business days.")],
    )

    assert result.sufficient
    assert result.reason == "supported_evidence"


def test_gate_rejects_retrieved_but_unsupported_question() -> None:
    result = DeterministicEvidenceGate().assess(
        "What pet insurance provider and premium does the company use?",
        [_chunk("The expense policy covers business meals and travel receipts.")],
    )

    assert not result.sufficient
    assert result.reason == "insufficient_query_overlap"


def test_gate_rejects_explicitly_conflicting_facts() -> None:
    result = DeterministicEvidenceGate().assess(
        "Which conflicting portal value is correct?",
        [
            _chunk("The VPN portal is vpn-a.example.", "one"),
            _chunk("The VPN portal is vpn-b.example.", "two"),
        ],
    )

    assert not result.sufficient
    assert result.reason == "conflicting_evidence"


def test_gate_allows_historical_evidence_when_it_matches_question() -> None:
    result = DeterministicEvidenceGate().assess(
        "What was the Starter price in 2025?",
        [_chunk("The Starter price was $29 in 2025.")],
        historical_intent=True,
    )

    assert result.sufficient
