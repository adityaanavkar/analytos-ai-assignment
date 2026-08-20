"""Focused tests for the minimal RAG orchestration path."""

from collections.abc import Sequence

import pytest

from app.rag.models import RetrievedChunk
from app.rag.service import RagService


class FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FakeSearch:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.indexed: tuple[Sequence[RetrievedChunk], Sequence[Sequence[float]]] | None = None

    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        self.indexed = (chunks, vectors)

    def search(
        self,
        query: str,
        vector: Sequence[float],
        *,
        top: int,
    ) -> list[RetrievedChunk]:
        return self.chunks[:top]


class FakeGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        return self.answer


def _chunk(chunk_id: str = "pricing-2026-1") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        content="Enterprise support is included.",
        title="Pricing 2026",
        source_path="KnowledgeBase/Pricing2026.pdf",
        page_number=2,
    )


@pytest.mark.asyncio
async def test_answer_returns_only_verified_citations() -> None:
    chunk = _chunk()
    service = RagService(
        FakeEmbedder(),
        FakeSearch([chunk]),
        FakeGenerator("Support is included [pricing-2026-1]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == "Support is included [pricing-2026-1]."
    assert result.citations[0].chunk_id == chunk.id
    assert result.citations[0].page == 2
    assert result.retrieved_chunks == 1


@pytest.mark.asyncio
async def test_answer_rejects_a_citation_not_present_in_retrieval() -> None:
    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("Support is included [invented-chunk]."),
    )

    with pytest.raises(ValueError, match="were not retrieved"):
        await service.answer(question="Is support included?", top_k=5)


@pytest.mark.asyncio
async def test_answer_refuses_without_calling_generation_when_search_is_empty() -> None:
    service = RagService(FakeEmbedder(), FakeSearch([]), FakeGenerator("must not be returned"))

    result = await service.answer(question="What is the vacation policy?", top_k=5)

    assert result.citations == ()
    assert result.retrieved_chunks == 0
    assert "could not find" in result.answer


def test_index_embeds_and_passes_aligned_vectors_to_search() -> None:
    chunks = [_chunk("one"), _chunk("two")]
    search = FakeSearch([])
    service = RagService(FakeEmbedder(), search, FakeGenerator("unused"))

    service.index(chunks)

    expected_vectors = [[float(len(chunk.content))] for chunk in chunks]
    assert search.indexed == (chunks, expected_vectors)
