"""Deterministic fusion of retrieval results produced for decomposed queries."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.rag.models import RetrievedChunk

MAX_SUBQUERIES = 3
MAX_FUSED_CANDIDATES = 20

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


@dataclass(frozen=True, slots=True)
class _Candidate:
    """Fusion metadata kept separate from the public chunk model."""

    chunk: RetrievedChunk
    coverage: int
    best_rank: int
    best_score: float
    first_subquery: int
    subquery_indices: frozenset[int]


def fuse_subquery_results(
    results: Sequence[Sequence[RetrievedChunk]],
    *,
    comparison: bool = False,
    limit: int = MAX_FUSED_CANDIDATES,
) -> list[RetrievedChunk]:
    """Fuse at most three ordered result lists into a bounded ranked list.

    Stable chunk IDs are preferred as identities. When IDs differ, matching
    source paths and content hashes (or normalized content) are treated as the
    same evidence. Coverage across distinct subqueries is rewarded before best
    retrieval score, rank, and input order provide deterministic tie breakers.
    Comparison mode reserves representatives for every version family found
    in the input, so fusion cannot silently discard one side of a comparison.
    """

    if len(results) > MAX_SUBQUERIES:
        raise ValueError(f"fusion accepts at most {MAX_SUBQUERIES} subqueries")
    if not 1 <= limit <= MAX_FUSED_CANDIDATES:
        raise ValueError(f"limit must be between 1 and {MAX_FUSED_CANDIDATES}")

    candidates: dict[str, _Candidate] = {}
    aliases: dict[str, str] = {}
    for subquery_index, chunks in enumerate(results):
        seen_in_subquery: set[str] = set()
        for rank, chunk in enumerate(chunks):
            id_identity = f"id:{chunk.id}"
            content_identity = _content_identity(chunk)
            identity = aliases.get(id_identity) or aliases.get(content_identity) or id_identity
            if identity in seen_in_subquery:
                continue
            seen_in_subquery.add(identity)
            previous = candidates.get(identity)
            score = chunk.score if chunk.score is not None else 0.0
            if previous is None:
                candidates[identity] = _Candidate(
                    chunk=chunk,
                    coverage=1,
                    best_rank=rank,
                    best_score=score,
                    first_subquery=subquery_index,
                    subquery_indices=frozenset({subquery_index}),
                )
                aliases[id_identity] = identity
                aliases[content_identity] = identity
                continue
            preferred = _prefer(chunk, rank, score, previous)
            candidates[identity] = _Candidate(
                chunk=preferred,
                coverage=previous.coverage + 1,
                best_rank=min(previous.best_rank, rank),
                best_score=max(previous.best_score, score),
                first_subquery=min(previous.first_subquery, subquery_index),
                subquery_indices=previous.subquery_indices | frozenset({subquery_index}),
            )

    ordered = sorted(candidates.values(), key=_sort_key)
    if comparison:
        ordered = _reserve_version_families(ordered, limit)
    return [candidate.chunk for candidate in ordered[:limit]]


def _content_identity(chunk: RetrievedChunk) -> str:
    content = chunk.content_hash or " ".join(chunk.content.casefold().split())
    return f"content:{chunk.source_path.casefold()}|{content}"


def _prefer(
    chunk: RetrievedChunk,
    rank: int,
    score: float,
    previous: _Candidate,
) -> RetrievedChunk:
    """Keep the best duplicate payload, with stable tie-breaking."""

    if score > previous.best_score or (score == previous.best_score and rank < previous.best_rank):
        return chunk
    return previous.chunk


def _sort_key(candidate: _Candidate) -> tuple[float, float, int, int]:
    return (
        -candidate.coverage,
        -candidate.best_score,
        candidate.best_rank,
        candidate.first_subquery,
    )


def _reserve_version_families(candidates: list[_Candidate], limit: int) -> list[_Candidate]:
    """Place one candidate from each version family before filling.

    Comparison retrieval runs a query per requested version. A generic chunk can
    therefore occur in every result list and receive a high coverage score even
    though it does not contain the requested version's exact fact. Preserve
    version-specific evidence first within each family, then use score and rank
    as tie breakers. This keeps both sides of a comparison grounded in their own
    evidence instead of letting cross-query coverage choose the representative.
    """

    families: dict[str, _Candidate] = {}
    for candidate in candidates:
        family = _version_family(candidate.chunk)
        previous = families.get(family)
        if previous is None or _comparison_family_key(candidate) < _comparison_family_key(previous):
            families[family] = candidate
    reserved = sorted(families.values(), key=_comparison_sort_key)[:limit]
    reserved_ids = {id(candidate) for candidate in reserved}
    remainder = [candidate for candidate in candidates if id(candidate) not in reserved_ids]
    return reserved + remainder


def _comparison_family_key(candidate: _Candidate) -> tuple[int, float, int, int]:
    """Rank a family representative, preferring side-specific evidence.

    ``len(subquery_indices) == 1`` means the chunk was retrieved for one side
    only. It is more useful for a comparison than a generic chunk retrieved for
    multiple sides, so specificity is ordered before coverage and score.
    """

    return (
        0 if len(candidate.subquery_indices) == 1 else 1,
        -candidate.best_score,
        candidate.best_rank,
        candidate.first_subquery,
    )


def _comparison_sort_key(candidate: _Candidate) -> tuple[float, float, int, int]:
    """Order reserved representatives deterministically across families."""

    return (
        float(_comparison_family_key(candidate)[0]),
        -candidate.best_score,
        candidate.best_rank,
        candidate.first_subquery,
    )


def _version_family(chunk: RetrievedChunk) -> str:
    if chunk.document_type:
        version = chunk.version or _year_from_source(chunk.source_path) or "unspecified"
        return "|".join(
            (
                (chunk.department or "").casefold(),
                chunk.document_type.casefold(),
                version.casefold(),
            )
        )
    stem = PurePosixPath(chunk.source_path.replace("\\", "/")).stem.casefold()
    return re.sub(r"[^a-z0-9]+", "", stem)


def _year_from_source(source_path: str) -> str | None:
    match = _YEAR_RE.search(source_path)
    return match.group(0) if match else None
