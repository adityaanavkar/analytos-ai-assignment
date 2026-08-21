import json
from pathlib import Path

import pytest

from evaluation.usage_cost import (
    TOKEN_ESTIMATION_METHOD,
    build_usage_cost_evidence,
    estimate_text_tokens,
    estimate_usage,
    load_pricing_assumptions,
)


def test_versioned_pricing_assumptions_are_explicit_and_dated() -> None:
    assumptions = load_pricing_assumptions()

    assert assumptions.schema_version == 1
    assert assumptions.pricing_id == "azure-openai-assignment-estimate-v1"
    assert assumptions.effective_date.isoformat() == "2026-08-21"
    assert assumptions.currency == "USD"
    assert set(assumptions.models) == {"text-embedding-3-small", "gpt-4.1-mini"}
    assert "not an Azure billing quote" in assumptions.source_note


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("abcd", 1),
        ("abcde", 2),
        ("€", 1),
        ("€€", 2),
    ],
)
def test_token_estimation_is_deterministic_over_utf8_bytes(text: str, expected: int) -> None:
    assert estimate_text_tokens(text) == expected


def test_usage_keeps_embedding_chat_input_and_output_separate() -> None:
    usage = estimate_usage(
        embedding_inputs=["a" * 100],
        chat_inputs=["b" * 20, "c" * 20],
        chat_output="d" * 20,
    )

    assert usage.estimation_method == TOKEN_ESTIMATION_METHOD
    assert usage.embedding_input_tokens == 25
    assert usage.chat_input_tokens == 10
    assert usage.chat_output_tokens == 5
    assert usage.total_tokens == 40


def test_cost_evidence_uses_dated_prices_and_serializes_exact_decimal_strings() -> None:
    evidence = build_usage_cost_evidence(
        embedding_inputs=["a" * 100],
        chat_inputs=["b" * 40],
        chat_output="c" * 20,
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4.1-mini",
    )

    assert evidence.cost.embedding_cost == "0.000000500000"
    assert evidence.cost.chat_input_cost == "0.000004000000"
    assert evidence.cost.chat_output_cost == "0.000008000000"
    assert evidence.cost.total_cost == "0.000012500000"
    serialized = json.loads(evidence.to_json())
    assert serialized["usage"]["total_tokens"] == 40
    assert serialized["cost"]["pricing_effective_date"] == "2026-08-21"
    assert "provider-side hidden tokens are excluded" in serialized["cost"]["approximation_warning"]


def test_unknown_model_cannot_silently_receive_a_price() -> None:
    with pytest.raises(ValueError, match="No pricing assumption for chat model"):
        build_usage_cost_evidence(
            embedding_inputs=[],
            chat_inputs=[],
            chat_output="",
            embedding_model="text-embedding-3-small",
            chat_model="unknown-chat-model",
        )


def test_loader_rejects_an_undated_or_changed_schema(tmp_path: Path) -> None:
    invalid = tmp_path / "pricing.json"
    invalid.write_text('{"schema_version": 2}', encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        load_pricing_assumptions(invalid)
