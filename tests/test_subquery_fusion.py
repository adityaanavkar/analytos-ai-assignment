"""Focused tests for bounded, deterministic query-result fusion."""

import pytest

from app.rag.models import RetrievedChunk
from app.rag.subquery_fusion import MAX_FUSED_CANDIDATES, fuse_subquery_results


def _chunk(
    chunk_id: str,
    text: str,
    *,
    score: float,
    source: str = "KnowledgeBase/Policy.pdf",
    is_current: bool | None = None,
    department: str | None = None,
    document_type: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        content=text,
        title="Policy",
        source_path=source,
        score=score,
        is_current=is_current,
        department=department,
        document_type=document_type,
    )


def test_duplicate_fusion_keeps_best_duplicate_and_rewards_coverage() -> None:
    result = fuse_subquery_results(
        [
            [_chunk("shared", "old", score=0.4), _chunk("one", "one", score=0.9)],
            [_chunk("shared", "best", score=0.8), _chunk("two", "two", score=0.9)],
        ],
    )
    assert [chunk.id for chunk in result] == ["shared", "one", "two"]
    assert result[0].content == "best"


def test_content_identity_deduplicates_different_chunk_ids_from_same_source() -> None:
    result = fuse_subquery_results(
        [
            [_chunk("first-id", "same evidence", score=0.6)],
            [_chunk("second-id", "  SAME   EVIDENCE ", score=0.8)],
        ],
    )
    assert [chunk.id for chunk in result] == ["second-id"]


def test_fusion_is_deterministic_for_equal_scores() -> None:
    inputs = [[_chunk("b", "b", score=1.0), _chunk("a", "a", score=1.0)]]
    assert [chunk.id for chunk in fuse_subquery_results(inputs)] == ["b", "a"]
    assert fuse_subquery_results(inputs) == fuse_subquery_results(inputs)


def test_comparison_reserves_both_version_families() -> None:
    result = fuse_subquery_results(
        [
            [
                _chunk(
                    "current",
                    "2026",
                    score=1.0,
                    source="KnowledgeBase/Sales/Pricing2026.pdf",
                    is_current=True,
                    department="Sales",
                    document_type="rate_card",
                ),
                _chunk(
                    "current-2",
                    "2026 extra",
                    score=0.99,
                    source="KnowledgeBase/Sales/Pricing2026.pdf",
                    is_current=True,
                    department="Sales",
                    document_type="rate_card",
                ),
            ],
            [
                _chunk(
                    "old",
                    "2025",
                    score=0.2,
                    source="KnowledgeBase/Sales/Pricing2025.pdf",
                    is_current=False,
                    department="Sales",
                    document_type="rate_card",
                )
            ],
        ],
        comparison=True,
        limit=2,
    )
    assert {chunk.id for chunk in result} == {"current", "old"}


def test_comparison_prefers_side_specific_evidence_over_shared_generic_chunk() -> None:
    """A shared generic chunk must not replace exact evidence for either year."""

    result = fuse_subquery_results(
        [
            [
                _chunk(
                    "generic-2025",
                    "Starter pricing changed by approximately 8-10%.",
                    score=1.0,
                    source="KnowledgeBase/Sales/Pricing2025.pdf",
                    is_current=False,
                    department="Sales",
                    document_type="rate_card",
                ),
                _chunk(
                    "exact-2025",
                    "Starter price is $29 in 2025.",
                    score=0.7,
                    source="KnowledgeBase/Sales/Pricing2025.pdf",
                    is_current=False,
                    department="Sales",
                    document_type="rate_card",
                ),
                _chunk(
                    "generic-2026",
                    "Starter pricing changed by approximately 8-10%.",
                    score=1.0,
                    source="KnowledgeBase/Sales/Pricing2026.pdf",
                    is_current=True,
                    department="Sales",
                    document_type="rate_card",
                ),
            ],
            [
                _chunk(
                    "generic-2025",
                    "Starter pricing changed by approximately 8-10%.",
                    score=1.0,
                    source="KnowledgeBase/Sales/Pricing2025.pdf",
                    is_current=False,
                    department="Sales",
                    document_type="rate_card",
                ),
                _chunk(
                    "generic-2026",
                    "Starter pricing changed by approximately 8-10%.",
                    score=1.0,
                    source="KnowledgeBase/Sales/Pricing2026.pdf",
                    is_current=True,
                    department="Sales",
                    document_type="rate_card",
                ),
                _chunk(
                    "exact-2026",
                    "Starter price is $32 in 2026.",
                    score=0.7,
                    source="KnowledgeBase/Sales/Pricing2026.pdf",
                    is_current=True,
                    department="Sales",
                    document_type="rate_card",
                ),
            ],
        ],
        comparison=True,
        limit=2,
    )

    assert [chunk.id for chunk in result] == ["exact-2025", "exact-2026"]


def test_fusion_bounds_subqueries_and_candidates() -> None:
    with pytest.raises(ValueError, match="at most 3"):
        fuse_subquery_results([[], [], [], []])
    chunks = [_chunk(str(index), str(index), score=1.0) for index in range(25)]
    assert len(fuse_subquery_results([chunks])) == MAX_FUSED_CANDIDATES
