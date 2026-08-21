"""Request-scoped diagnostic traces kept outside the public chat contract."""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from app.rag.models import RetrievedChunk
from app.rag.query_analysis import QueryAnalysis
from evaluation.usage_cost import UsageCostEvidence, build_usage_cost_evidence

EMBEDDING_PRICING_MODEL = "text-embedding-3-small"
CHAT_PRICING_MODEL = "gpt-4.1-mini"


class DeploymentAware(Protocol):
    """Optional adapter metadata used only for diagnostics."""

    @property
    def embedding_deployment(self) -> str: ...

    @property
    def chat_deployment(self) -> str: ...


class GenerationInputProvider(Protocol):
    """Optional adapter hook exposing the exact captured generation text."""

    def generation_input_texts(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """One ranked retrieval result with its complete observable provenance."""

    rank: int
    id: str
    content: str
    title: str
    source_path: str
    page_number: int | None
    section: str | None
    score: float | None
    document_id: str | None
    content_hash: str | None
    file_type: str | None
    department: str | None
    document_type: str | None
    version: str | None
    effective_from: str | None
    effective_to: str | None
    is_current: bool | None
    sheet_name: str | None
    table_number: int | None
    row_number: int | None
    allowed_groups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageLatency:
    """Wall-clock duration of each observable RAG stage in milliseconds."""

    embedding_ms: float
    retrieval_ms: float
    generation_ms: float
    total_ms: float


@dataclass(frozen=True, slots=True)
class QueryAnalysisSnapshot:
    """Structured A7 analysis metadata captured for evaluation and debugging."""

    standalone_query: str
    ambiguous: bool
    clarification: str | None
    temporal_intent: str
    subqueries: tuple[str, ...]
    resolved_from_context: bool


@dataclass(frozen=True, slots=True)
class RequestTrace:
    """Complete evaluation trace for one answer invocation."""

    question: str
    embedding_deployment: str
    generation_deployment: str
    candidates: tuple[CandidateSnapshot, ...]
    generation_output: str | None
    stage_latency: StageLatency
    usage_cost: UsageCostEvidence
    selected_context: tuple[CandidateSnapshot, ...] = ()
    analysis: QueryAnalysisSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible trace for an evaluation artifact."""

        return asdict(self)


class RequestTraceStore:
    """Keep the latest trace isolated to the current async request context."""

    def __init__(self, name: str) -> None:
        self._current: ContextVar[RequestTrace | None] = ContextVar(name, default=None)

    def clear(self) -> None:
        """Prevent a failed or new request from exposing an older trace."""

        self._current.set(None)

    def set(self, trace: RequestTrace) -> None:
        """Attach a completed trace to the current request context."""

        self._current.set(trace)

    def get(self) -> RequestTrace | None:
        """Return only the trace visible in the current request context."""

        return self._current.get()


def candidate_snapshots(chunks: Sequence[RetrievedChunk]) -> tuple[CandidateSnapshot, ...]:
    """Freeze ranked search results before downstream generation can obscure them."""

    return tuple(
        CandidateSnapshot(
            rank=rank,
            id=chunk.id,
            content=chunk.content,
            title=chunk.title,
            source_path=chunk.source_path,
            page_number=chunk.page_number,
            section=chunk.section,
            score=chunk.score,
            document_id=chunk.document_id,
            content_hash=chunk.content_hash,
            file_type=chunk.file_type,
            department=chunk.department,
            document_type=chunk.document_type,
            version=chunk.version,
            effective_from=chunk.effective_from.isoformat() if chunk.effective_from else None,
            effective_to=chunk.effective_to.isoformat() if chunk.effective_to else None,
            is_current=chunk.is_current,
            sheet_name=chunk.sheet_name,
            table_number=chunk.table_number,
            row_number=chunk.row_number,
            allowed_groups=chunk.allowed_groups,
        )
        for rank, chunk in enumerate(chunks, start=1)
    )


def _deployment(component: object, attribute: str) -> str:
    value = getattr(component, attribute, None)
    return value if isinstance(value, str) and value else "unknown"


def _generation_inputs(
    generator: object,
    question: str,
    chunks: Sequence[RetrievedChunk],
) -> tuple[str, ...]:
    provider = getattr(generator, "generation_input_texts", None)
    if callable(provider):
        values = provider(question, chunks)
        if isinstance(values, tuple) and all(isinstance(value, str) for value in values):
            return values
    return (question, *(chunk.content for chunk in chunks))


def build_request_trace(
    *,
    question: str,
    embedder: object,
    generator: object,
    chunks: Sequence[RetrievedChunk],
    candidates: Sequence[RetrievedChunk] | None = None,
    generation_output: str | None,
    stage_latency: StageLatency,
    embedding_was_called: bool,
    generation_was_called: bool,
    embedding_inputs: Sequence[str] | None = None,
    analysis: QueryAnalysis | None = None,
) -> RequestTrace:
    """Build trace evidence without changing the chat response model."""

    measured_embedding_inputs = (
        tuple(embedding_inputs)
        if embedding_inputs is not None
        else ((question,) if embedding_was_called else ())
    )
    chat_inputs = _generation_inputs(generator, question, chunks) if generation_was_called else ()
    usage_cost = build_usage_cost_evidence(
        embedding_inputs=measured_embedding_inputs,
        chat_inputs=chat_inputs,
        chat_output=generation_output or "",
        embedding_model=EMBEDDING_PRICING_MODEL,
        chat_model=CHAT_PRICING_MODEL,
    )
    return RequestTrace(
        question=question,
        embedding_deployment=_deployment(embedder, "embedding_deployment"),
        generation_deployment=_deployment(generator, "chat_deployment"),
        candidates=candidate_snapshots(candidates if candidates is not None else chunks),
        generation_output=generation_output,
        stage_latency=stage_latency,
        usage_cost=usage_cost,
        selected_context=candidate_snapshots(chunks),
        analysis=(
            QueryAnalysisSnapshot(
                standalone_query=analysis.standalone_query,
                ambiguous=analysis.ambiguous,
                clarification=analysis.clarification,
                temporal_intent=analysis.temporal_intent.value,
                subqueries=tuple(analysis.subqueries),
                resolved_from_context=analysis.resolved_from_context,
            )
            if analysis is not None
            else None
        ),
    )
