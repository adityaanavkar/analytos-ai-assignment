"""Focused tests for the minimal RAG orchestration path."""

from collections.abc import Sequence

import pytest

from app.rag.models import RetrievedChunk
from app.rag.service import GREETING_ANSWER, INSUFFICIENT_EVIDENCE_ANSWER, RagService


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
async def test_answer_replaces_a_fabricated_citation_with_safe_refusal() -> None:
    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("Support is included [invented-chunk]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 1


@pytest.mark.asyncio
async def test_answer_refuses_without_calling_generation_when_search_is_empty() -> None:
    service = RagService(FakeEmbedder(), FakeSearch([]), FakeGenerator("must not be returned"))

    result = await service.answer(question="What is the vacation policy?", top_k=5)

    assert result.citations == ()
    assert result.retrieved_chunks == 0
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER


@pytest.mark.asyncio
async def test_hi_returns_a_deterministic_greeting_without_azure_calls() -> None:
    class UnexpectedEmbedder:
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise AssertionError("a greeting must not call Azure OpenAI")

    service = RagService(UnexpectedEmbedder(), FakeSearch([]), FakeGenerator("unused"))

    result = await service.answer(question="Hi", top_k=5)

    assert result.answer == GREETING_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 0


@pytest.mark.asyncio
async def test_nonsense_with_uncited_generation_returns_safe_refusal() -> None:
    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("I cannot answer that from the supplied evidence."),
    )

    result = await service.answer(question="whjat", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 1


def test_index_embeds_and_passes_aligned_vectors_to_search() -> None:
    chunks = [_chunk("one"), _chunk("two")]
    search = FakeSearch([])
    service = RagService(FakeEmbedder(), search, FakeGenerator("unused"))

    service.index(chunks)

    expected_vectors = [[float(len(chunk.content))] for chunk in chunks]
    assert search.indexed == (chunks, expected_vectors)
