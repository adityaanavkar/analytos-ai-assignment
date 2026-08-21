"""Frozen, intentionally simple vector-only baseline orchestration."""

import asyncio
from collections.abc import Sequence
from time import perf_counter
from typing import Protocol

from app.rag.models import ChatResult, RetrievedChunk
from app.rag.service import INSUFFICIENT_EVIDENCE_ANSWER, RagService
from app.rag.trace import RequestTrace, RequestTraceStore, StageLatency, build_request_trace


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
        self._traces = RequestTraceStore(f"baseline-request-trace-{id(self)}")

    def get_last_trace(self) -> RequestTrace | None:
        """Return diagnostics for the current request context, if completed."""

        return self._traces.get()

    def _record_trace(
        self,
        *,
        question: str,
        chunks: Sequence[RetrievedChunk],
        generation_output: str | None,
        request_started: float,
        embedding_ms: float,
        retrieval_ms: float,
        generation_ms: float = 0.0,
        generation_was_called: bool = False,
    ) -> None:
        self._traces.set(
            build_request_trace(
                question=question,
                embedder=self._embedder,
                generator=self._generator,
                chunks=chunks,
                generation_output=generation_output,
                stage_latency=StageLatency(
                    embedding_ms=embedding_ms,
                    retrieval_ms=retrieval_ms,
                    generation_ms=generation_ms,
                    total_ms=round((perf_counter() - request_started) * 1000, 2),
                ),
                embedding_was_called=True,
                generation_was_called=generation_was_called,
            )
        )

    async def answer(self, *, question: str, top_k: int = 5) -> ChatResult:
        """Answer through vector-only Top 5, ignoring caller retrieval overrides."""

        request_started = perf_counter()
        self._traces.clear()
        del top_k
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        embedding_started = perf_counter()
        query_vectors = await asyncio.to_thread(self._embedder.embed, [normalized_question])
        embedding_ms = round((perf_counter() - embedding_started) * 1000, 2)
        if len(query_vectors) != 1:
            raise ValueError("query embedding response must contain exactly one vector")

        retrieval_started = perf_counter()
        chunks = await asyncio.to_thread(self._search.search, query_vectors[0])
        retrieval_ms = round((perf_counter() - retrieval_started) * 1000, 2)
        if not chunks:
            result = ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=0,
            )
            self._record_trace(
                question=normalized_question,
                chunks=(),
                generation_output=None,
                request_started=request_started,
                embedding_ms=embedding_ms,
                retrieval_ms=retrieval_ms,
            )
            return result

        generation_started = perf_counter()
        answer = await asyncio.to_thread(self._generator.generate, normalized_question, chunks)
        generation_ms = round((perf_counter() - generation_started) * 1000, 2)
        citations = RagService._resolve_citations(answer, chunks)
        if not citations:
            result = ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=len(chunks),
            )
        else:
            result = ChatResult(answer=answer, citations=citations, retrieved_chunks=len(chunks))
        self._record_trace(
            question=normalized_question,
            chunks=chunks,
            generation_output=answer,
            request_started=request_started,
            embedding_ms=embedding_ms,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            generation_was_called=True,
        )
        return result
