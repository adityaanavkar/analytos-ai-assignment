"""Regression tests for deterministic improved-context selection."""

from app.rag.models import RetrievedChunk
from app.rag.retrieval_policy import has_historical_intent, select_retrieval_context


def _chunk(
    chunk_id: str,
    content: str,
    *,
    source: str = "KnowledgeBase/Sales/Discounts.xlsx",
    title: str = "Discounts",
    current: bool | None = None,
    document_type: str | None = None,
    sheet: str | None = None,
    table: int | None = None,
    row: int | None = None,
    section: str | None = None,
    content_hash: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        content=content,
        title=title,
        source_path=source,
        content_hash=content_hash,
        file_type="xlsx" if source.endswith(".xlsx") else "pdf",
        department="Sales",
        document_type=document_type,
        is_current=current,
        sheet_name=sheet,
        table_number=table,
        row_number=row,
        section=section,
    )


def test_current_query_suppresses_stale_chunks_from_same_document_family() -> None:
    candidates = [
        _chunk(
            "old",
            "Professional tier costs $59 and includes 75,000 API calls.",
            source="KnowledgeBase/Sales/Pricing2025.pdf",
            title="Pricing 2025",
            current=False,
            document_type="rate_card",
        ),
        _chunk(
            "current",
            "Professional tier costs $65 and includes 100,000 API calls.",
            source="KnowledgeBase/Sales/Pricing2026.pdf",
            title="Pricing 2026",
            current=True,
            document_type="rate_card",
        ),
    ]

    result = select_retrieval_context(
        "What are the current Professional tier price and API limit?", candidates
    )

    assert [chunk.id for chunk in result] == ["current"]


def test_comparison_query_retains_both_historical_and_current_versions() -> None:
    candidates = [
        _chunk(
            "current",
            "Starter is $32 and Advanced Analytics is $14 in 2026.",
            source="KnowledgeBase/Sales/Pricing2026.pdf",
            title="Pricing 2026",
            current=True,
            document_type="rate_card",
        ),
        _chunk(
            "old",
            "Starter was $29 and Advanced Analytics was $12 in 2025.",
            source="KnowledgeBase/Sales/Pricing2025.pdf",
            title="Pricing 2025",
            current=False,
            document_type="rate_card",
        ),
    ]

    result = select_retrieval_context(
        "Compare Starter and Advanced Analytics prices in 2025 and 2026.", candidates
    )

    assert {chunk.id for chunk in result} == {"old", "current"}
    assert has_historical_intent("Compare 2025 versus 2026 pricing")


def test_comparison_keeps_exact_pricing_evidence_ahead_of_novel_spreadsheet_rows() -> None:
    """Both exact version prices survive a six-chunk comparison shortlist."""

    candidates = [
        _chunk(
            "generic-2026",
            "Starter prices increased in 2026.",
            source="KnowledgeBase/Sales/Pricing2026.pdf",
            title="Pricing 2026",
            current=True,
            document_type="rate_card",
        ),
        _chunk(
            "exact-2026",
            "The Starter price in 2026 is $32 per seat per month.",
            source="KnowledgeBase/Sales/Pricing2026.pdf",
            title="Pricing 2026",
            current=True,
            document_type="rate_card",
        ),
        _chunk(
            "exact-2025",
            "The Starter price in 2025 was $29 per seat per month.",
            source="KnowledgeBase/Sales/Pricing2025.pdf",
            title="Pricing 2025",
            current=False,
            document_type="rate_card",
        ),
        *[
            _chunk(
                f"distractor-{index}",
                "A Professional discount example uses a $65 reference list price.",
                source=f"KnowledgeBase/Sales/Discounts{index}.xlsx",
            )
            for index in range(1, 6)
        ],
    ]

    result = select_retrieval_context(
        "Compare the Starter price in 2025 and 2026.",
        candidates,
    )

    assert len(result) <= 6
    assert "exact-2026" in {chunk.id for chunk in result}
    assert "exact-2025" in {chunk.id for chunk in result}


def test_explicit_single_year_does_not_trigger_current_only_filtering() -> None:
    candidates = [
        _chunk(
            "current",
            "Starter is $32 in 2026.",
            source="KnowledgeBase/Sales/Pricing2026.pdf",
            current=True,
            document_type="rate_card",
        ),
        _chunk(
            "old",
            "Starter was $29 in 2025.",
            source="KnowledgeBase/Sales/Pricing2025.pdf",
            current=False,
            document_type="rate_card",
        ),
    ]

    result = select_retrieval_context("What did Starter cost in 2025?", candidates)

    assert "old" in {chunk.id for chunk in result}


def test_spreadsheet_question_collects_relevant_rows_across_sections() -> None:
    candidates = [
        _chunk("noise", "General sales notes", sheet="Notes", row=2),
        _chunk(
            "volume",
            "Seat Count Tier=101-250; Discount %=20%",
            sheet="Volume Discounts",
            table=1,
            row=9,
        ),
        _chunk(
            "neighbor",
            "Seat Count Tier=251-500; Discount %=25%",
            sheet="Volume Discounts",
            table=1,
            row=10,
        ),
        _chunk(
            "term",
            "Billing Term=Annual prepaid; Discount %=15%",
            sheet="Term Discounts",
            table=1,
            row=6,
        ),
        _chunk(
            "approval",
            "Combined Discount=35%; Approver=Chief Revenue Officer and Finance Business Partner",
            sheet="Approval Thresholds",
            table=1,
            row=8,
        ),
        _chunk(
            "price",
            "250 seats annual prepaid; combined discount=35%; final price=$42.25",
            sheet="Calculation Examples",
            table=2,
            row=4,
        ),
    ]

    result = select_retrieval_context(
        "For 250 seats annual prepaid, what discount, final price, and approver apply?",
        candidates,
        limit=4,
    )

    assert {chunk.id for chunk in result} == {"volume", "term", "approval", "price"}


def test_broad_requirements_question_keeps_concrete_table_rows() -> None:
    candidates = [
        _chunk(
            "heading",
            "All company passwords must meet these requirements.",
            source="KnowledgeBase/IT/PasswordPolicy.docx",
            title="Password Policy",
            section="Password Requirements",
        ),
        _chunk(
            "purpose",
            "This policy protects company systems.",
            source="KnowledgeBase/IT/PasswordPolicy.docx",
            title="Password Policy",
            section="Purpose",
        ),
        _chunk(
            "length",
            "Requirement: Minimum length | Standard: 12 characters",
            source="KnowledgeBase/IT/PasswordPolicy.docx",
            title="Password Policy",
            section="Password Requirements",
            table=1,
            row=2,
        ),
        _chunk(
            "reuse",
            "Requirement: Reuse | Standard: Cannot reuse the last 10 passwords",
            source="KnowledgeBase/IT/PasswordPolicy.docx",
            title="Password Policy",
            section="Password Requirements",
            table=1,
            row=4,
        ),
    ]

    result = select_retrieval_context("What are the company password requirements?", candidates)

    assert [chunk.id for chunk in result[:2]] == ["length", "reuse"]


def test_startup_discount_question_reserves_special_program_evidence() -> None:
    """A startup query must retain its program rules beside volume and term context."""

    candidates = [
        _chunk(
            "volume-group",
            "Seat count tiers and volume discounts apply by contracted seats.",
            sheet="Volume Discounts",
            section="Volume Discounts grouped rows 1-25",
        ),
        _chunk(
            "term-group",
            "Annual prepaid term discounts can combine with volume discounts.",
            sheet="Term Discounts",
            section="Term Discounts grouped rows 1-10",
        ),
        _chunk(
            "special-group",
            "Program=Startup Year 1; Discount %=0.3; do not stack with volume or term "
            "discounts; annual re-verification.",
            sheet="Special Programs",
            section="Special Programs grouped rows 1-10",
        ),
        _chunk(
            "volume-row",
            "Seat Count Tier=5-24 seats; Discount %=0",
            sheet="Volume Discounts",
            row=7,
        ),
        _chunk(
            "term-row",
            "Billing Term=Monthly; Discount %=0",
            sheet="Term Discounts",
            row=5,
        ),
    ]

    result = select_retrieval_context(
        "Can the Year 1 startup discount stack with volume or term discounts, "
        "what is its rate, and how often is eligibility checked?",
        candidates,
        limit=3,
    )

    assert len(result) == 3
    assert "special-group" in {chunk.id for chunk in result}


def test_selection_deduplicates_and_preserves_multi_document_evidence() -> None:
    candidates = [
        _chunk(
            "travel",
            "Submit trip expenses within 30 calendar days.",
            source="KnowledgeBase/Finance/TravelPolicy.docx",
            title="Travel Policy",
            section="Submission",
            content_hash="same-travel-content",
        ),
        _chunk(
            "travel-copy",
            "Submit trip expenses within 30 calendar days.",
            source="KnowledgeBase/Finance/TravelPolicy.docx",
            title="Travel Policy",
            section="Submission",
            content_hash="same-travel-content",
        ),
        _chunk(
            "expense",
            "$3,000 requires Department VP approval; receipts required at $25.",
            source="KnowledgeBase/Finance/ExpensePolicy.pdf",
            title="Expense Policy",
            section="Approvals",
        ),
    ]

    result = select_retrieval_context(
        "When submit a $3,000 travel expense, what receipt threshold and who approves?",
        candidates,
    )

    assert [chunk.id for chunk in result] == ["expense", "travel"]


def test_same_content_from_different_sources_is_not_deduplicated() -> None:
    candidates = [
        _chunk(
            "nda",
            "Trade secrets remain protected indefinitely.",
            source="KnowledgeBase/Legal/NDA.docx",
            content_hash="shared-clause",
        ),
        _chunk(
            "vendor",
            "Trade secrets remain protected indefinitely.",
            source="KnowledgeBase/Legal/VendorContract.pdf",
            content_hash="shared-clause",
        ),
    ]

    result = select_retrieval_context("How are trade secrets protected?", candidates)

    assert {chunk.id for chunk in result} == {"nda", "vendor"}


def test_policy_rejects_unbounded_candidate_sets_and_invalid_limits() -> None:
    candidates = [_chunk(str(index), str(index)) for index in range(21)]

    try:
        select_retrieval_context("question", candidates)
    except ValueError as error:
        assert "at most 20" in str(error)
    else:
        raise AssertionError("expected candidate cap validation")

    try:
        select_retrieval_context("question", candidates[:1], limit=7)
    except ValueError as error:
        assert "between 1 and 6" in str(error)
    else:
        raise AssertionError("expected context limit validation")
