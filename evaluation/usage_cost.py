"""Deterministic token and cost estimates for reproducible RAG evaluations."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

DEFAULT_PRICING_ASSUMPTIONS = Path("evaluation/pricing/azure_openai_assumptions_v1.json")
TOKEN_ESTIMATION_METHOD = "utf8-bytes-divided-by-4-v1"
_ONE_MILLION = Decimal(1_000_000)
_COST_PRECISION = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Input and output prices for one model under one dated assumption set."""

    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal


@dataclass(frozen=True, slots=True)
class PricingAssumptions:
    """Versioned prices and provenance used by an evaluation run."""

    schema_version: int
    pricing_id: str
    effective_date: date
    currency: str
    source_note: str
    token_estimation_method: str
    token_estimation_description: str
    models: Mapping[str, ModelPricing]


@dataclass(frozen=True, slots=True)
class EstimatedUsage:
    """Estimated tokens derived only from caller-supplied captured text."""

    estimation_method: str
    embedding_input_tokens: int
    chat_input_tokens: int
    chat_output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class EstimatedCost:
    """Dated model prices and their calculated USD cost components."""

    pricing_id: str
    pricing_effective_date: str
    currency: str
    embedding_model: str
    chat_model: str
    embedding_input_usd_per_million_tokens: str
    chat_input_usd_per_million_tokens: str
    chat_output_usd_per_million_tokens: str
    embedding_cost: str
    chat_input_cost: str
    chat_output_cost: str
    total_cost: str
    approximation_warning: str


@dataclass(frozen=True, slots=True)
class UsageCostEvidence:
    """Serializable usage and cost evidence attached to one evaluated request."""

    usage: EstimatedUsage
    cost: EstimatedCost

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible object without losing decimal precision."""

        return asdict(self)

    def to_json(self) -> str:
        """Serialize evidence in stable, review-friendly JSON."""

        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _non_negative_decimal(value: object, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - normalize malformed JSON values
        raise ValueError(f"{field} must be a decimal number") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a finite non-negative decimal number")
    return amount


def load_pricing_assumptions(
    path: Path = DEFAULT_PRICING_ASSUMPTIONS,
) -> PricingAssumptions:
    """Load and validate one immutable, versioned pricing assumption file."""

    raw = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported pricing assumptions schema_version")

    token_estimation = raw.get("token_estimation")
    if not isinstance(token_estimation, dict):
        raise ValueError("token_estimation must be an object")
    method = _required_string(token_estimation.get("method_id"), "token_estimation.method_id")
    if method != TOKEN_ESTIMATION_METHOD:
        raise ValueError(f"Unsupported token estimation method: {method}")

    raw_models = raw.get("models")
    if not isinstance(raw_models, dict) or not raw_models:
        raise ValueError("models must be a non-empty object")
    models: dict[str, ModelPricing] = {}
    for raw_name, raw_price in raw_models.items():
        model_name = _required_string(raw_name, "models key")
        if not isinstance(raw_price, dict):
            raise ValueError(f"models.{model_name} must be an object")
        models[model_name] = ModelPricing(
            input_usd_per_million_tokens=_non_negative_decimal(
                raw_price.get("input_usd_per_million_tokens"),
                f"models.{model_name}.input_usd_per_million_tokens",
            ),
            output_usd_per_million_tokens=_non_negative_decimal(
                raw_price.get("output_usd_per_million_tokens"),
                f"models.{model_name}.output_usd_per_million_tokens",
            ),
        )

    effective_date_text = _required_string(raw.get("effective_date"), "effective_date")
    try:
        effective_date = date.fromisoformat(effective_date_text)
    except ValueError as exc:
        raise ValueError("effective_date must use ISO YYYY-MM-DD format") from exc

    return PricingAssumptions(
        schema_version=1,
        pricing_id=_required_string(raw.get("pricing_id"), "pricing_id"),
        effective_date=effective_date,
        currency=_required_string(raw.get("currency"), "currency"),
        source_note=_required_string(raw.get("source_note"), "source_note"),
        token_estimation_method=method,
        token_estimation_description=_required_string(
            token_estimation.get("description"),
            "token_estimation.description",
        ),
        models=models,
    )


def estimate_text_tokens(text: str) -> int:
    """Estimate tokens as ceil(UTF-8 bytes / 4), with empty text equal to zero."""

    byte_count = len(text.encode("utf-8"))
    return (byte_count + 3) // 4 if byte_count else 0


def estimate_usage(
    *,
    embedding_inputs: Sequence[str],
    chat_inputs: Sequence[str],
    chat_output: str,
) -> EstimatedUsage:
    """Estimate each billable token category from the captured request text."""

    embedding_tokens = sum(estimate_text_tokens(text) for text in embedding_inputs)
    chat_input_tokens = sum(estimate_text_tokens(text) for text in chat_inputs)
    chat_output_tokens = estimate_text_tokens(chat_output)
    return EstimatedUsage(
        estimation_method=TOKEN_ESTIMATION_METHOD,
        embedding_input_tokens=embedding_tokens,
        chat_input_tokens=chat_input_tokens,
        chat_output_tokens=chat_output_tokens,
        total_tokens=embedding_tokens + chat_input_tokens + chat_output_tokens,
    )


def _component_cost(tokens: int, price_per_million: Decimal) -> Decimal:
    return (Decimal(tokens) * price_per_million / _ONE_MILLION).quantize(_COST_PRECISION)


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def build_usage_cost_evidence(
    *,
    embedding_inputs: Sequence[str],
    chat_inputs: Sequence[str],
    chat_output: str,
    embedding_model: str,
    chat_model: str,
    assumptions: PricingAssumptions | None = None,
) -> UsageCostEvidence:
    """Calculate reproducible approximate usage and cost from captured text."""

    resolved = assumptions or load_pricing_assumptions()
    try:
        embedding_price = resolved.models[embedding_model]
    except KeyError as exc:
        raise ValueError(f"No pricing assumption for embedding model: {embedding_model}") from exc
    try:
        chat_price = resolved.models[chat_model]
    except KeyError as exc:
        raise ValueError(f"No pricing assumption for chat model: {chat_model}") from exc

    usage = estimate_usage(
        embedding_inputs=embedding_inputs,
        chat_inputs=chat_inputs,
        chat_output=chat_output,
    )
    embedding_cost = _component_cost(
        usage.embedding_input_tokens,
        embedding_price.input_usd_per_million_tokens,
    )
    chat_input_cost = _component_cost(
        usage.chat_input_tokens,
        chat_price.input_usd_per_million_tokens,
    )
    chat_output_cost = _component_cost(
        usage.chat_output_tokens,
        chat_price.output_usd_per_million_tokens,
    )
    total_cost = embedding_cost + chat_input_cost + chat_output_cost

    return UsageCostEvidence(
        usage=usage,
        cost=EstimatedCost(
            pricing_id=resolved.pricing_id,
            pricing_effective_date=resolved.effective_date.isoformat(),
            currency=resolved.currency,
            embedding_model=embedding_model,
            chat_model=chat_model,
            embedding_input_usd_per_million_tokens=_decimal_text(
                embedding_price.input_usd_per_million_tokens
            ),
            chat_input_usd_per_million_tokens=_decimal_text(
                chat_price.input_usd_per_million_tokens
            ),
            chat_output_usd_per_million_tokens=_decimal_text(
                chat_price.output_usd_per_million_tokens
            ),
            embedding_cost=_decimal_text(embedding_cost),
            chat_input_cost=_decimal_text(chat_input_cost),
            chat_output_cost=_decimal_text(chat_output_cost),
            total_cost=_decimal_text(total_cost),
            approximation_warning=(
                f"Token counts use {resolved.token_estimation_method}. "
                f"{resolved.token_estimation_description} {resolved.source_note}"
            ),
        ),
    )
