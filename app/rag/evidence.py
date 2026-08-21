"""Deterministic evidence sufficiency checks for grounded generation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.rag.models import RetrievedChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_FACT_RE = re.compile(r"\b(?:is|are|was|were|costs?|priced at)\s+([^.;\n]+)", re.IGNORECASE)
_CONFLICT_RE = re.compile(
    r"\b(?:conflict|conflicting|contradict|contradictory|discrepanc|correct|disagree|inconsistent)",
    re.IGNORECASE,
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "can",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "this",
        "to",
        "what",
        "when",
        "which",
        "who",
        "with",
        "would",
        "should",
        "tell",
        "me",
        "please",
    }
)


class EvidenceGate(Protocol):
    """Checks whether retrieved chunks provide a defensible answer basis."""

    def assess(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
        *,
        historical_intent: bool = False,
    ) -> EvidenceDecision: ...


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    """Auditable result of the pre-generation evidence check."""

    sufficient: bool
    reason: str
    query_terms: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()


class DeterministicEvidenceGate:
    """Reject retrieval that has too little lexical support for the question.

    The threshold is intentionally configurable so it can be calibrated on a
    training split without changing the service orchestration.
    """

    def __init__(self, *, minimum_query_token_hits: int = 2) -> None:
        if minimum_query_token_hits < 1:
            raise ValueError("minimum_query_token_hits must be positive")
        self.minimum_query_token_hits = minimum_query_token_hits

    def assess(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
        *,
        historical_intent: bool = False,
    ) -> EvidenceDecision:
        del historical_intent
        query_terms = tuple(sorted(set(_tokens(question)) - _STOP_WORDS))
        if not chunks:
            return EvidenceDecision(False, "no_retrieved_evidence", query_terms=query_terms)
        evidence_terms = set().union(*(_tokens(_evidence_text(chunk)) for chunk in chunks))
        matched_terms = tuple(sorted(set(query_terms) & evidence_terms))
        if _CONFLICT_RE.search(question) and _has_conflicting_facts(question, chunks):
            return EvidenceDecision(
                False,
                "conflicting_evidence",
                query_terms=query_terms,
                matched_terms=matched_terms,
            )
        required_hits = min(self.minimum_query_token_hits, 1 if len(query_terms) <= 2 else 2)
        if len(matched_terms) < required_hits:
            return EvidenceDecision(
                False,
                "insufficient_query_overlap",
                query_terms=query_terms,
                matched_terms=matched_terms,
            )
        return EvidenceDecision(
            True,
            "supported_evidence",
            query_terms=query_terms,
            matched_terms=matched_terms,
        )


def _evidence_text(chunk: RetrievedChunk) -> str:
    return " ".join(
        value for value in (chunk.content, chunk.title, chunk.section, chunk.sheet_name) if value
    )


def _tokens(value: str) -> list[str]:
    return [_stem(token) for token in _TOKEN_RE.findall(value.casefold())]


def _stem(token: str) -> str:
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


def _has_conflicting_facts(question: str, chunks: Sequence[RetrievedChunk]) -> bool:
    query_terms = set(_tokens(question)) - _STOP_WORDS
    relevant = [chunk for chunk in chunks if query_terms & set(_tokens(_evidence_text(chunk)))]
    signatures = {signature for chunk in relevant for signature in _fact_signatures(chunk.content)}
    return len(signatures) > 1


def _fact_signatures(content: str) -> set[str]:
    return {" ".join(_tokens(match.group(1))[:8]) for match in _FACT_RE.finditer(content)}
