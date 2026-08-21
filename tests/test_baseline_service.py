"""Focused tests for the frozen baseline orchestration contract."""

from collections.abc import Sequence

import pytest

from app.baseline.service import BaselineService
from app.rag.models import RetrievedChunk
from app.rag.service import INSUFFICIENT_EVIDENCE_ANSWER


class FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class FakeSearch:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.vectors: list[list[float]] = []

    def search(self, vector: Sequence[float]) -> list[RetrievedChunk]:
        self.vectors.append(list(vector))
        return self.chunks


class FakeGenerator:
    def __init__(self, answer: str) -> None:
        self.answer_text = answer

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        return self.answer_text


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        id="expense-1",
        content="Submit expenses within 30 days.",
        title="Expense Policy",
        source_path="Finance/ExpensePolicy.pdf",
        page_number=1,
    )


@pytest.mark.asyncio
async def test_baseline_answers_with_verified_citations() -> None:
    search = FakeSearch([_chunk()])
    service = BaselineService(
        FakeEmbedder(),
        search,
        FakeGenerator("Submit within 30 days [expense-1]."),
    )

    result = await service.answer(question="When should expenses be submitted?", top_k=20)

    assert result.answer == "Submit within 30 days [expense-1]."
    assert result.citations[0].chunk_id == "expense-1"
    assert result.retrieved_chunks == 1
    assert search.vectors == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_baseline_refuses_when_vector_search_is_empty() -> None:
    service = BaselineService(
        FakeEmbedder(),
        FakeSearch([]),
        FakeGenerator("must not be used"),
    )

    result = await service.answer(question="Unknown question", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 0


@pytest.mark.asyncio
async def test_baseline_rejects_unretrieved_citations_without_an_error() -> None:
    service = BaselineService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("Invented answer [unknown-chunk]."),
    )

    result = await service.answer(question="Unknown question", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 1
