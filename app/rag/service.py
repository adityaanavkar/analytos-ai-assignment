"""Orchestration for a simple retrieve-then-generate RAG request."""

import asyncio
import re
from collections.abc import Sequence
from typing import Protocol

from app.rag.models import ChatResult, Citation, RetrievedChunk

_CITATION_PATTERN = re.compile(r"\[([^\[\]\s]+)\]")


class Embedder(Protocol):
    """Creates one embedding for each supplied text."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChunkSearch(Protocol):
    """Indexes and retrieves knowledge-base chunks."""

    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None: ...

    def search(
        self,
        query: str,
        vector: Sequence[float],
        *,
        top: int,
    ) -> list[RetrievedChunk]: ...


class GroundedGenerator(Protocol):
    """Generates an answer from explicitly supplied evidence."""

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str: ...


class RagService:
    """Minimal service interface shared by the API and tests."""

    def __init__(
        self,
        embedder: Embedder,
        search: ChunkSearch,
        generator: GroundedGenerator,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._generator = generator

    def index(self, chunks: Sequence[RetrievedChunk]) -> None:
        """Embed and upload chunks while preserving input order."""

        if not chunks:
            return
        vectors = self._embedder.embed([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("embedding count does not match chunk count")
        self._search.index(chunks, vectors)

    async def answer(self, *, question: str, top_k: int) -> ChatResult:
        """Retrieve relevant chunks, generate an answer, and verify citations."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")

        query_vectors = await asyncio.to_thread(self._embedder.embed, [normalized_question])
        if len(query_vectors) != 1:
            raise ValueError("query embedding response must contain exactly one vector")

        chunks = await asyncio.to_thread(
            self._search.search,
            normalized_question,
            query_vectors[0],
            top=top_k,
        )
        if not chunks:
            return ChatResult(
                answer="I could not find supporting information in the knowledge base.",
                citations=(),
                retrieved_chunks=0,
            )

        answer = await asyncio.to_thread(self._generator.generate, normalized_question, chunks)
        citations = self._resolve_citations(answer, chunks)
        return ChatResult(answer=answer, citations=citations, retrieved_chunks=len(chunks))

    @staticmethod
    def _resolve_citations(
        answer: str,
        chunks: Sequence[RetrievedChunk],
    ) -> tuple[Citation, ...]:
        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        cited_ids = list(dict.fromkeys(_CITATION_PATTERN.findall(answer)))
        unknown_ids = [chunk_id for chunk_id in cited_ids if chunk_id not in chunks_by_id]
        if unknown_ids:
            joined = ", ".join(unknown_ids)
            raise ValueError(f"answer contains citations that were not retrieved: {joined}")
        if not cited_ids:
            raise ValueError("grounded answer must cite at least one retrieved chunk")

        return tuple(
            Citation(
                chunk_id=chunk_id,
                source=chunks_by_id[chunk_id].source_path,
                page=chunks_by_id[chunk_id].page_number,
                section=chunks_by_id[chunk_id].section,
            )
            for chunk_id in cited_ids
        )
