"""Deterministic context selection for the improved RAG pipeline.

The search adapter is responsible for producing a broad, ranked candidate set.
This module turns that set into a small relevance-first evidence pack without
another network call, which keeps the policy independently testable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from app.rag.models import RetrievedChunk

MAX_CANDIDATES = 20
MAX_CONTEXT_CHUNKS = 6

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CURRENCY_RE = re.compile(r"(?:[$€£]\s?\d|\b(?:usd|eur|gbp)\b)", re.IGNORECASE)
_PRICE_WORDS = frozenset({"cost", "costs", "price", "prices", "pricing", "rate", "rates"})
_NUMERIC_VALUE_WORDS = frozenset({"length", "limit", "maximum", "minimum", "threshold"})
_HISTORICAL_WORDS = frozenset(
    {
        "compare",
        "compared",
        "difference",
        "historical",
        "history",
        "old",
        "older",
        "previous",
        "prior",
        "versus",
        "vs",
    }
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "does",
        "for",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "which",
        "who",
        "with",
    }
)


def has_historical_intent(question: str) -> bool:
    """Return whether a query intentionally asks for historical evidence."""

    tokens = set(_tokens(question))
    years = set(_YEAR_RE.findall(question))
    # A single explicit year is also version intent. Filtering it as "stale"
    # would make a direct question about the 2025 rate card impossible.
    return bool(tokens & _HISTORICAL_WORDS) or bool(years)


def select_retrieval_context(
    question: str,
    candidates: Sequence[RetrievedChunk],
    *,
    limit: int = MAX_CONTEXT_CHUNKS,
    historical_intent: bool | None = None,
) -> list[RetrievedChunk]:
    """Select a deterministic, deduplicated, version-aware evidence pack.

    Candidates must arrive in descending retrieval rank and are deliberately
    capped so this local policy cannot conceal an unbounded search operation.
    """

    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"retrieval policy accepts at most {MAX_CANDIDATES} candidates")
    if not 1 <= limit <= MAX_CONTEXT_CHUNKS:
        raise ValueError(f"limit must be between 1 and {MAX_CONTEXT_CHUNKS}")

    unique = _deduplicate(candidates)
    if re.search(r"\brate\s+cards?\b", question, re.IGNORECASE):
        rate_cards = [
            chunk
            for chunk in unique
            if chunk.document_type and chunk.document_type.endswith("rate_card")
        ]
        if rate_cards:
            unique = rate_cards
    preserve_historical = (
        has_historical_intent(question) if historical_intent is None else historical_intent
    )
    if not preserve_historical:
        unique = _prefer_current_versions(unique)
    ranked = _rank(question, unique, prefer_current=not preserve_historical)
    requirement_rows = _reserve_structured_requirement_rows(question, ranked, limit=limit)
    if requirement_rows:
        selected_ids = {chunk.id for chunk in requirement_rows}
        return [
            *requirement_rows,
            *(chunk for chunk in ranked if chunk.id not in selected_ids),
        ][:limit]
    return _diversified_selection(question, ranked, limit=limit)


def _reserve_structured_requirement_rows(
    question: str,
    ranked: Sequence[RetrievedChunk],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    """Keep concrete table standards for broad requirements questions."""

    query_tokens = set(_tokens(question)) - _STOP_WORDS
    if not query_tokens & {"requirement", "requirements"}:
        return []
    subject_tokens = query_tokens - {"company", "requirement", "requirements"}
    if not subject_tokens:
        return []
    rows = [
        chunk
        for chunk in ranked
        if chunk.table_number is not None
        and chunk.row_number is not None
        and not chunk.content.casefold().startswith("table headers:")
        and subject_tokens
        & set(_tokens(" ".join(value for value in (chunk.title, chunk.section) if value)))
    ]
    return rows[:limit]


def _deduplicate(candidates: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in candidates:
        normalized_content = " ".join(chunk.content.casefold().split())
        content_identity = chunk.content_hash or normalized_content or chunk.id
        identity = f"{_source_key(chunk)}|{content_identity}"
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(chunk)
    return unique


def _prefer_current_versions(candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    current_families = {_version_family(chunk) for chunk in candidates if chunk.is_current is True}
    return [
        chunk
        for chunk in candidates
        if not (chunk.is_current is False and _version_family(chunk) in current_families)
    ]


def _version_family(chunk: RetrievedChunk) -> str:
    if chunk.document_type:
        return "|".join(part.casefold() for part in (chunk.department or "", chunk.document_type))
    name = PurePosixPath(chunk.source_path.replace("\\", "/")).stem.casefold()
    normalized_name = _YEAR_RE.sub("", name)
    return re.sub(r"[^a-z0-9]+", "", normalized_name or name)


def _rank(
    question: str,
    candidates: list[RetrievedChunk],
    *,
    prefer_current: bool,
) -> list[RetrievedChunk]:
    query_tokens = set(_tokens(question)) - _STOP_WORDS
    query_numbers = {token for token in query_tokens if token.isdigit()}
    asks_for_price = bool(query_tokens & _PRICE_WORDS)
    asks_for_numeric_value = bool(query_tokens & _NUMERIC_VALUE_WORDS)
    indexed = list(enumerate(candidates))

    token_sets = [_chunk_tokens(chunk) for chunk in candidates]
    relevant_spreadsheet_rows = [
        chunk
        for chunk, tokens in zip(candidates, token_sets, strict=True)
        if chunk.file_type == "xlsx" and query_tokens & tokens
    ]

    def score(item: tuple[int, RetrievedChunk]) -> tuple[float, int]:
        rank, chunk = item
        chunk_tokens = token_sets[rank]
        lexical_hits = len(query_tokens & chunk_tokens)
        number_hits = len(query_numbers & chunk_tokens)
        # Current-version preference is useful for an unspecified/current
        # question, but it must not distort explicit historical or comparison
        # queries where both version families are evidence.
        current_bonus = 1.5 if prefer_current and chunk.is_current is True else 0.0
        spreadsheet_bonus = 0.75 if chunk.file_type == "xlsx" and lexical_hits else 0.0
        currency_bonus = 1.5 if asks_for_price and _CURRENCY_RE.search(chunk.content) else 0.0
        rate_card_bonus = (
            1.0
            if asks_for_price
            and chunk.document_type is not None
            and chunk.document_type.endswith("rate_card")
            and _CURRENCY_RE.search(chunk.content)
            else 0.0
        )
        numeric_value_bonus = (
            2.0 if asks_for_numeric_value and re.search(r"\d", chunk.content) else 0.0
        )
        neighbor_bonus = (
            0.5 if _has_related_spreadsheet_row(chunk, relevant_spreadsheet_rows) else 0.0
        )
        rank_score = (len(candidates) - rank) / max(len(candidates), 1)
        total = (
            rank_score
            + lexical_hits
            + (2.0 * number_hits)
            + current_bonus
            + spreadsheet_bonus
            + currency_bonus
            + rate_card_bonus
            + numeric_value_bonus
            + neighbor_bonus
        )
        return (-total, rank)

    return [chunk for _, chunk in sorted(indexed, key=score)]


def _chunk_tokens(chunk: RetrievedChunk) -> set[str]:
    searchable = " ".join(
        value
        for value in (
            chunk.title,
            chunk.source_path,
            chunk.section,
            chunk.sheet_name,
            chunk.content,
        )
        if value
    )
    return set(_tokens(searchable))


def _has_related_spreadsheet_row(
    chunk: RetrievedChunk,
    relevant_rows: Sequence[RetrievedChunk],
) -> bool:
    """Recognize adjacent rows so a matching row can carry table context with it."""

    if chunk.file_type != "xlsx" or chunk.row_number is None:
        return False
    return any(
        other.id != chunk.id
        and _source_key(other) == _source_key(chunk)
        and other.sheet_name == chunk.sheet_name
        and other.table_number == chunk.table_number
        and other.row_number is not None
        and abs(other.row_number - chunk.row_number) == 1
        for other in relevant_rows
    )


def _diversified_selection(
    question: str,
    ranked: list[RetrievedChunk],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    """Return the strongest ranked evidence, with diversity kept secondary.

    The ranker already combines lexical overlap, numeric overlap, document
    version, and spreadsheet-neighbor evidence.  Earlier versions let source
    and bucket novelty choose from the entire candidate list, so an unrelated
    spreadsheet row could displace an exact pricing chunk.  The context pack
    is therefore a strict relevance shortlist; source and bucket diversity may
    still be represented by that shortlist, but can never displace a stronger
    lexical or numeric match.
    """

    # Grouped spreadsheet chunks are intentionally retained when a question
    # combines independent table facts such as volume, term, and approval.
    # The grouped chunk is the bounded table context that lets generation
    # recover from a misleading top row.  This reservation is facet-based and
    # only applies when those chunks are actually present in the candidate set.
    # It does not reserve arbitrary spreadsheet novelty, so exact PDF rate-card
    # evidence remains ahead of unrelated rows in price comparisons.
    reserved = _reserve_grouped_spreadsheet_evidence(question, ranked, limit=limit)
    if not reserved:
        return ranked[:limit]
    selected_ids = {chunk.id for chunk in reserved}
    return [
        *reserved,
        *(chunk for chunk in ranked if chunk.id not in selected_ids),
    ][:limit]


def _reserve_grouped_spreadsheet_evidence(
    question: str,
    ranked: Sequence[RetrievedChunk],
    *,
    limit: int,
) -> list[RetrievedChunk]:
    """Reserve the strongest grouped chunk for each requested table facet.

    A grouped chunk is a compact, deterministic representation of one XLSX
    sheet.  Multi-fact questions need more than the single best row because a
    row from the approval table can be semantically plausible but belong to a
    different discount range.  The reservation is capped at three chunks and
    requires at least two requested facets, keeping ordinary spreadsheet
    lookups strictly relevance-first.
    """

    # Historical and comparison requests must keep their version evidence
    # available for the version-aware policy below.  In particular, an exact
    # 2025/$29 or 2026/$32 rate-card chunk must never be displaced by a
    # grouped operational spreadsheet context.
    if has_historical_intent(question):
        return []

    grouped = [
        chunk
        for chunk in ranked
        if chunk.file_type == "xlsx"
        and chunk.section
        and "grouped rows" in chunk.section.casefold()
    ]
    if not grouped:
        return []

    query_tokens = set(_tokens(question)) - _STOP_WORDS
    facets: list[tuple[str, frozenset[str]]] = [
        ("volume", frozenset({"seat", "seats", "volume", "tier", "quantity"})),
        (
            "term",
            frozenset({"term", "annual", "prepaid", "monthly", "yearly", "billing"}),
        ),
        (
            "approval",
            frozenset({"approval", "approvals", "approve", "approver", "authorize"}),
        ),
        (
            "program",
            frozenset({"startup", "program", "eligibility", "eligible", "stack", "stacking"}),
        ),
        (
            "calculation",
            frozenset({"calculate", "calculation", "combined", "final", "price", "cost"}),
        ),
    ]
    requested = [name for name, markers in facets if query_tokens & markers]
    if len(requested) < 2:
        return []

    reserved: list[RetrievedChunk] = []
    for facet in requested:
        candidates = [
            chunk
            for chunk in grouped
            if _group_matches_facet(chunk, facet) and chunk.id not in {item.id for item in reserved}
        ]
        if candidates:
            # ``ranked`` is already deterministically scored.  Taking the
            # first match preserves that score ordering within a facet.
            reserved.append(candidates[0])
        if len(reserved) >= min(3, limit):
            break
    return reserved


def _group_matches_facet(chunk: RetrievedChunk, facet: str) -> bool:
    tokens = _chunk_tokens(chunk)
    sheet = (chunk.sheet_name or "").casefold()
    section = (chunk.section or "").casefold()
    if facet == "volume":
        return bool(tokens & {"seat", "seats", "volume", "tier", "quantity"}) or "volume" in sheet
    if facet == "term":
        return (
            bool(tokens & {"term", "annual", "prepaid", "monthly", "yearly", "billing"})
            or "term" in sheet
        )
    if facet == "approval":
        return (
            bool(tokens & {"approval", "approvals", "approve", "approver", "authorize"})
            or "approval" in sheet
        )
    if facet == "program":
        return (
            bool(tokens & {"startup", "program", "eligibility", "eligible", "stack", "stacking"})
            or "special" in sheet
        )
    return (
        bool(tokens & {"calculate", "calculation", "combined", "final", "price", "cost"})
        or "calculation" in section
    )


def _source_key(chunk: RetrievedChunk) -> str:
    return chunk.source_path.replace("\\", "/").casefold()


def _tokens(value: str) -> list[str]:
    return [_canonical_token(token) for token in _TOKEN_RE.findall(value.casefold())]


def _canonical_token(token: str) -> str:
    """Normalize common inflections used in approval questions and tables."""

    if token in {
        "approve",
        "approves",
        "approved",
        "approver",
        "approvers",
        "approval",
        "approvals",
        "authorize",
        "authorizes",
        "authorized",
        "authorization",
    }:
        return "approval"
    return token
