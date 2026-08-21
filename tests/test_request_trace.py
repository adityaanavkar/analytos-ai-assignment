import asyncio
from collections.abc import Sequence
from datetime import date

import pytest

from app.baseline.service import BaselineService
from app.rag.models import IndexedDocument, RetrievedChunk
from app.rag.service import INSUFFICIENT_EVIDENCE_ANSWER, RagService


class TraceEmbedder:
    embedding_deployment = "embedding-deployment"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class TraceSearch:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks

    def search(
        self,
        query_or_vector: str | Sequence[float],
        vector: Sequence[float] | None = None,
        *,
        top: int = 5,
    ) -> list[RetrievedChunk]:
        del query_or_vector, vector
        return self.chunks[:top]

    def inventory(self) -> list[IndexedDocument]:
        return []

    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        del chunks, vectors


class BaselineTraceSearch:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks

    def search(self, vector: Sequence[float]) -> list[RetrievedChunk]:
        del vector
        return self.chunks


class TraceGenerator:
    chat_deployment = "chat-deployment"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        del question, chunks
        return self.answer

    def generation_input_texts(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> tuple[str, ...]:
        return "system prompt", f"question={question}; evidence={chunks[0].content}"


def _rich_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        id="pricing-row-5",
        content="Seats 200-499 receive 20 percent.",
        title="Discounts",
        source_path="KnowledgeBase/Sales/Discounts.xlsx",
        section="Volume Discounts row 5",
        score=0.91,
        document_id="document-1",
        content_hash="abc123",
        file_type="xlsx",
        department="Sales",
        document_type="discount_schedule",
        version="2026",
        effective_from=date(2026, 1, 1),
        is_current=True,
        sheet_name="Volume Discounts",
        table_number=1,
        row_number=5,
        allowed_groups=("sales", "finance"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["baseline", "improved"])
async def test_services_capture_ranked_candidates_usage_cost_and_latency(pipeline: str) -> None:
    chunk = _rich_chunk()
    generator = TraceGenerator("The discount is 20 percent [pricing-row-5].")
    service: BaselineService | RagService
    if pipeline == "baseline":
        service = BaselineService(
            TraceEmbedder(),
            BaselineTraceSearch([chunk]),
            generator,
        )
    else:
        service = RagService(TraceEmbedder(), TraceSearch([chunk]), generator)

    result = await service.answer(question="What is the discount?", top_k=5)
    trace = service.get_last_trace()

    assert result.answer == "The discount is 20 percent [pricing-row-5]."
    assert trace is not None
    assert trace.embedding_deployment == "embedding-deployment"
    assert trace.generation_deployment == "chat-deployment"
    assert trace.generation_output == result.answer
    assert trace.stage_latency.embedding_ms >= 0
    assert trace.stage_latency.retrieval_ms >= 0
    assert trace.stage_latency.generation_ms >= 0
    assert trace.stage_latency.total_ms >= 0
    assert trace.usage_cost.usage.embedding_input_tokens > 0
    assert trace.usage_cost.usage.chat_input_tokens > 0
    assert trace.usage_cost.usage.chat_output_tokens > 0
    assert trace.usage_cost.cost.pricing_effective_date == "2026-08-21"
    candidate = trace.candidates[0]
    assert candidate.rank == 1
    assert candidate.id == chunk.id
    assert candidate.content == chunk.content
    assert candidate.score == 0.91
    assert candidate.source_path == chunk.source_path
    assert candidate.sheet_name == "Volume Discounts"
    assert candidate.row_number == 5
    assert candidate.effective_from == "2026-01-01"
    assert candidate.allowed_groups == ("sales", "finance")
    assert trace.selected_context == trace.candidates


@pytest.mark.asyncio
async def test_trace_records_no_generation_for_unsupported_evidence() -> None:
    service = RagService(
        TraceEmbedder(),
        TraceSearch([_rich_chunk()]),
        TraceGenerator("Unsupported claim [invented-citation]."),
    )

    result = await service.answer(question="Invent something", top_k=5)
    trace = service.get_last_trace()

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert trace is not None
    assert trace.generation_output is None
    assert trace.candidates[0].content == _rich_chunk().content


@pytest.mark.asyncio
async def test_request_trace_is_isolated_between_concurrent_tasks() -> None:
    service = RagService(
        TraceEmbedder(),
        TraceSearch([_rich_chunk()]),
        TraceGenerator("The discount is documented [pricing-row-5]."),
    )

    async def invoke(question: str) -> str | None:
        await service.answer(question=question, top_k=5)
        trace = service.get_last_trace()
        return trace.question if trace else None

    observed = await asyncio.gather(invoke("Question one"), invoke("Question two"))

    assert tuple(observed) == ("Question one", "Question two")
