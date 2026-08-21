"""Focused tests for isolated A7 query analysis."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.rag.query_analysis import (
    AzureQueryAnalyzer,
    ConversationTurn,
    DeterministicQueryAnalyzer,
    QueryAnalysis,
    TemporalIntent,
)


def test_fallback_marks_unresolved_generic_question_ambiguous() -> None:
    result = DeterministicQueryAnalyzer().analyze("What is the limit?")
    assert result.ambiguous is True
    assert result.clarification
    assert result.subqueries == ["What is the limit?"]


def test_fallback_resolves_follow_up_from_recent_user_context() -> None:
    result = DeterministicQueryAnalyzer().analyze(
        "What about Standard?",
        [ConversationTurn(role="user", content="What is the cancellation policy for Enterprise?")],
    )
    assert result.resolved_from_context is True
    assert "cancellation policy" in result.standalone_query
    assert result.ambiguous is False


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What did Starter cost in 2025?", TemporalIntent.HISTORICAL),
        ("Compare 2025 versus 2026 pricing", TemporalIntent.COMPARISON),
    ],
)
def test_fallback_detects_temporal_intent(question: str, intent: TemporalIntent) -> None:
    assert DeterministicQueryAnalyzer().analyze(question).temporal_intent == intent


def test_fallback_decomposes_explicit_year_comparison() -> None:
    result = DeterministicQueryAnalyzer().analyze("Compare the Starter price in 2025 and 2026.")
    assert result.temporal_intent is TemporalIntent.COMPARISON
    assert len(result.subqueries) == 3
    assert "2025" in result.subqueries[1]
    assert "2026" in result.subqueries[2]
    assert "2026" not in result.subqueries[1]
    assert "2025" not in result.subqueries[2]


def test_schema_rejects_extra_fields_and_inconsistent_clarification() -> None:
    with pytest.raises(ValidationError):
        QueryAnalysis.model_validate({"standalone_query": "policy", "unexpected": "value"})
    with pytest.raises(ValidationError):
        QueryAnalysis(standalone_query="policy", clarification="Which policy?")


def test_provider_malformed_output_uses_safe_fallback() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]
    )
    result = AzureQueryAnalyzer(client, deployment="query").analyze("What is the limit?")
    assert result.ambiguous is True


def test_provider_validates_structured_output_and_caps_subqueries() -> None:
    client = Mock()
    content = (
        '{"standalone_query":"compare pricing","ambiguous":false,'
        '"clarification":null,"temporal_intent":"comparison",'
        '"subqueries":["2025 pricing","2026 pricing","third","fourth"],'
        '"resolved_from_context":false}'
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    result = AzureQueryAnalyzer(client, deployment="query").analyze("Compare pricing")
    assert len(result.subqueries) <= 3
    assert result.subqueries[0].casefold() == "compare pricing"


def test_provider_broad_comparison_output_is_decomposed_by_year() -> None:
    client = Mock()
    content = (
        '{"standalone_query":"Compare the Starter price in 2025 and 2026.",'
        '"ambiguous":false,"clarification":null,"temporal_intent":"comparison",'
        '"subqueries":["Compare the Starter price in 2025 and 2026."],'
        '"resolved_from_context":false}'
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )

    result = AzureQueryAnalyzer(client, deployment="query").analyze(
        "Compare the Starter price in 2025 and 2026."
    )

    assert result.subqueries == [
        "Compare the Starter price in 2025 and 2026.",
        "Starter price in 2025",
        "Starter price in 2026",
    ]


def test_provider_preserves_valid_year_sides_and_fills_missing_side() -> None:
    client = Mock()
    content = (
        '{"standalone_query":"Compare Starter pricing in 2025 and 2026",'
        '"ambiguous":false,"clarification":null,"temporal_intent":"comparison",'
        '"subqueries":["Starter pricing in 2025"],'
        '"resolved_from_context":false}'
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )

    result = AzureQueryAnalyzer(client, deployment="query").analyze(
        "Compare Starter pricing in 2025 and 2026"
    )

    assert result.subqueries == [
        "Compare Starter pricing in 2025 and 2026",
        "Starter pricing in 2025",
        "Starter pricing in 2026",
    ]
