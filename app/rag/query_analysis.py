"""Schema-validated query analysis for the improved RAG pipeline.

The analyzer is deliberately isolated from retrieval orchestration so its
fallback behavior can be tested without Azure credentials or a live index.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rag.retrieval_policy import has_historical_intent

MAX_QUERY_LENGTH = 2_000
MAX_HISTORY_TURNS = 6
MAX_SUBQUERIES = 3


class ConversationTurn(BaseModel):
    """One bounded turn supplied to query analysis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)


class TemporalIntent(StrEnum):
    """Version-selection intent inferred from the question."""

    CURRENT = "current"
    HISTORICAL = "historical"
    COMPARISON = "comparison"
    UNSPECIFIED = "unspecified"


class QueryAnalysis(BaseModel):
    """The only model allowed to cross from query analysis into retrieval."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    standalone_query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    ambiguous: bool = False
    clarification: str | None = Field(default=None, max_length=500)
    temporal_intent: TemporalIntent = TemporalIntent.UNSPECIFIED
    subqueries: list[str] = Field(default_factory=list, max_length=MAX_SUBQUERIES)
    resolved_from_context: bool = False

    @model_validator(mode="after")
    def validate_consistency(self) -> QueryAnalysis:
        if self.ambiguous and not self.clarification:
            raise ValueError("ambiguous analysis requires clarification")
        if not self.ambiguous and self.clarification is not None:
            raise ValueError("unambiguous analysis must not contain clarification")
        normalized = _deduplicate_queries([self.standalone_query, *self.subqueries])
        if len(normalized) > MAX_SUBQUERIES:
            raise ValueError("analysis contains more than three unique subqueries")
        self.subqueries = normalized
        return self


class QueryAnalyzer(Protocol):
    """Provider-independent query-analysis boundary."""

    def analyze(
        self,
        question: str,
        history: Sequence[ConversationTurn] = (),
    ) -> QueryAnalysis: ...


_FOLLOW_UP = re.compile(
    r"^(?:what about|and what about|how about|and|does that|is there|are there|what if)\b",
    re.IGNORECASE,
)
_GENERIC = re.compile(
    r"^(?:what(?:'s| is)|tell me about)\s+(?:the\s+)?"
    r"(?:limit|policy|price|cost|rate|exception|requirement)\??$",
    re.IGNORECASE,
)
_COMPARISON = re.compile(r"\b(?:compare|comparison|versus|vs\.?|difference between)\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _deduplicate_queries(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result[:MAX_SUBQUERIES]


def _comparison_years(*values: str) -> list[str]:
    """Return distinct explicit years in the order in which they appear."""

    years: list[str] = []
    seen: set[str] = set()
    for value in values:
        for year in _YEAR.findall(value):
            if year not in seen:
                seen.add(year)
                years.append(year)
    return years


def _comparison_subject(query: str) -> str:
    """Remove comparison scaffolding and years while preserving the subject."""

    subject = _YEAR.sub(" ", query)
    subject = re.sub(
        r"\b(?:difference\s+between|compare(?:d)?|comparison|versus|vs\.?)\b",
        " ",
        subject,
        flags=re.IGNORECASE,
    )
    subject = re.sub(r"\b(?:and|or)\b", " ", subject, flags=re.IGNORECASE)
    subject = re.sub(
        r"\b(?:in|for|from|between|to)\s*(?=[,.!?;:]|$)",
        " ",
        subject,
        flags=re.IGNORECASE,
    )
    subject = re.sub(r"\s+([,.!?;:])", r"\1", subject)
    subject = _normalize(subject).strip(" ,.!?;:")
    return re.sub(r"^(?:the|a|an)\s+", "", subject, flags=re.IGNORECASE)


def _year_query(query: str, year: str) -> str:
    subject = _comparison_subject(query)
    return f"{subject} in {year}" if subject else year


def _ensure_comparison_subqueries(question: str, analysis: QueryAnalysis) -> QueryAnalysis:
    """Guarantee one retrieval query per side of an explicit year comparison.

    Providers often return the correct broad question but omit the independent
    retrieval queries needed to find each version.  The deterministic expansion
    runs after schema validation, so malformed provider output still follows the
    normal safe fallback path.
    """

    if analysis.ambiguous:
        return analysis
    years = _comparison_years(analysis.standalone_query, question)
    is_comparison = analysis.temporal_intent is TemporalIntent.COMPARISON or (
        len(years) >= 2
        and _COMPARISON.search(f"{question} {analysis.standalone_query}") is not None
    )
    if not is_comparison or len(years) < 2:
        return analysis

    existing = list(analysis.subqueries)
    expanded = [analysis.standalone_query]
    for year in years[: MAX_SUBQUERIES - 1]:
        side = next(
            (query for query in existing if _YEAR.findall(query) == [year]),
            None,
        )
        expanded.append(side or _year_query(analysis.standalone_query, year))
    return QueryAnalysis(
        standalone_query=analysis.standalone_query,
        ambiguous=analysis.ambiguous,
        clarification=analysis.clarification,
        temporal_intent=TemporalIntent.COMPARISON,
        subqueries=_deduplicate_queries(expanded),
        resolved_from_context=analysis.resolved_from_context,
    )


def _recent_user_question(history: Sequence[ConversationTurn]) -> str | None:
    for turn in reversed(history[-MAX_HISTORY_TURNS:]):
        if turn.role == "user":
            return turn.content
    return None


def _fallback(question: str, history: Sequence[ConversationTurn]) -> QueryAnalysis:
    """Produce safe, deterministic analysis when no model result is usable."""

    normalized = _normalize(question)
    if not normalized:
        raise ValueError("question must not be empty")
    prior = _recent_user_question(history)
    resolved = False
    standalone = normalized
    if prior and _FOLLOW_UP.match(normalized):
        standalone = f"{_normalize(prior)} {normalized}"
        resolved = True

    if _GENERIC.fullmatch(normalized) and not resolved:
        return QueryAnalysis(
            standalone_query=standalone,
            ambiguous=True,
            clarification="Which document, plan, policy, or subject do you mean?",
            temporal_intent=TemporalIntent.UNSPECIFIED,
            resolved_from_context=False,
        )

    if _COMPARISON.search(standalone):
        intent = TemporalIntent.COMPARISON
    elif has_historical_intent(standalone):
        intent = TemporalIntent.HISTORICAL
    else:
        intent = TemporalIntent.UNSPECIFIED
    return _ensure_comparison_subqueries(
        question,
        QueryAnalysis(
            standalone_query=standalone,
            temporal_intent=intent,
            subqueries=[standalone],
            resolved_from_context=resolved,
        ),
    )


class DeterministicQueryAnalyzer:
    """Local analyzer useful in development, tests, and provider failure paths."""

    def analyze(
        self,
        question: str,
        history: Sequence[ConversationTurn] = (),
    ) -> QueryAnalysis:
        return _fallback(question, history)


QUERY_ANALYSIS_SYSTEM_PROMPT = """Analyze the latest user question for enterprise RAG retrieval.
Return JSON only with standalone_query, ambiguous, clarification, temporal_intent,
subqueries, and resolved_from_context. Rewrite follow-ups using only the bounded
recent conversation. Ask for clarification when the subject is not identifiable.
Use historical for explicit years or prior versions, comparison for compare,
versus, or difference requests, and at most three independent subqueries.
Do not answer the question or invent facts."""


class AzureQueryAnalyzer:
    """Structured Azure OpenAI analyzer with deterministic safe fallback."""

    def __init__(self, client: Any, *, deployment: str) -> None:
        self._client = client
        self._deployment = deployment

    def analyze(
        self,
        question: str,
        history: Sequence[ConversationTurn] = (),
    ) -> QueryAnalysis:
        def fallback() -> QueryAnalysis:
            return _fallback(question, history)

        try:
            bounded_history = history[-MAX_HISTORY_TURNS:]
            context = "\n".join(f"{turn.role}: {turn.content}" for turn in bounded_history)
            user_input = f"Conversation:\n{context or '(none)'}\n\nLatest question: {question}"
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": QUERY_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "query_analysis",
                        "strict": True,
                        "schema": QueryAnalysis.model_json_schema(),
                    },
                },
            )
            content = response.choices[0].message.content
            if not content:
                return fallback()
            raw: object = json.loads(content)
            if not isinstance(raw, dict):
                return fallback()
            return _ensure_comparison_subqueries(
                question,
                QueryAnalysis.model_validate(raw),
            )
        except TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError:
            return fallback()
        except Exception:
            # Provider SDK/network exceptions must never make retrieval unsafe.
            return fallback()
