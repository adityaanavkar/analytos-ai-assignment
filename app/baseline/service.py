"""Frozen, intentionally simple vector-only baseline orchestration."""

import asyncio
from collections.abc import Sequence
from typing import Protocol

from app.rag.models import ChatResult, RetrievedChunk
from app.rag.service import INSUFFICIENT_EVIDENCE_ANSWER, RagService


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class GroundedGenerator(Protocol):
    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str: ...


class BaselineRetriever(Protocol):
    def search(self, vector: Sequence[float]) -> list[RetrievedChunk]: ...


class BaselineService:
    """Answer standalone questions with the frozen vector-only baseline."""

    def __init__(
        self,
        embedder: Embedder,
        search: BaselineRetriever,
        generator: GroundedGenerator,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._generator = generator

    async def answer(self, *, question: str, top_k: int = 5) -> ChatResult:
        """Answer through vector-only Top 5, ignoring caller retrieval overrides."""

        del top_k
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        query_vectors = await asyncio.to_thread(self._embedder.embed, [normalized_question])
        if len(query_vectors) != 1:
            raise ValueError("query embedding response must contain exactly one vector")

        chunks = await asyncio.to_thread(self._search.search, query_vectors[0])
        if not chunks:
            return ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=0,
            )

        answer = await asyncio.to_thread(self._generator.generate, normalized_question, chunks)
        citations = RagService._resolve_citations(answer, chunks)
        if not citations:
            return ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=len(chunks),
            )
        return ChatResult(answer=answer, citations=citations, retrieved_chunks=len(chunks))
