"""Orchestration for a simple retrieve-then-generate RAG request."""

import asyncio
import re
from collections.abc import Sequence
from pathlib import PurePosixPath
from time import perf_counter
from typing import Protocol

from app.rag.evidence import DeterministicEvidenceGate, EvidenceGate
from app.rag.models import ChatResult, Citation, IndexedDocument, RetrievedChunk
from app.rag.query_analysis import (
    ConversationTurn,
    DeterministicQueryAnalyzer,
    QueryAnalysis,
    QueryAnalyzer,
    TemporalIntent,
)
from app.rag.retrieval_policy import MAX_CANDIDATES, MAX_CONTEXT_CHUNKS, select_retrieval_context
from app.rag.subquery_fusion import fuse_subquery_results
from app.rag.trace import RequestTrace, RequestTraceStore, StageLatency, build_request_trace

# The generator contract is deliberately strict: a citation is exactly one
# retrieved chunk ID inside square brackets.  In particular, do not accept
# human-readable locators such as ``[chunk-id, row 10]`` because the model may
# attach a row/page that belongs to a different chunk.
_CITATION_BLOCK_PATTERN = re.compile(r"\[([^\[\]]*)\]")
_NESTED_CITATION_PATTERN = re.compile(r"\[\s*\[([^\[\]]+)\]\s*\]")
_GREETING_PATTERN = re.compile(
    r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))(?:\s+there)?[!.,?\s]*$",
    re.IGNORECASE,
)
_DOCUMENT_PATTERN = re.compile(r"\b(?:documents?|files?)\b", re.IGNORECASE)
_INVENTORY_PATTERN = re.compile(
    r"\b(?:available|indexed|index|list|inventory|total|how\s+many|what\s+all)\b"
    r"|\bin\s+(?:the\s+)?(?:rag|knowledge\s+base|index)\b",
    re.IGNORECASE,
)
_COUNT_PATTERN = re.compile(r"\b(?:how\s+many|total(?:\s+number)?|number\s+of)\b", re.IGNORECASE)

GREETING_ANSWER = "Hi! Ask me a question about the company knowledge base."
INSUFFICIENT_EVIDENCE_ANSWER = (
    "I could not find enough supporting information in the knowledge base to answer that."
)


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

    def inventory(self) -> list[IndexedDocument]: ...


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
        analyzer: QueryAnalyzer | None = None,
        evidence_gate: EvidenceGate | None = None,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._generator = generator
        self._analyzer = analyzer or DeterministicQueryAnalyzer()
        self._evidence_gate = evidence_gate or DeterministicEvidenceGate()
        self._traces = RequestTraceStore(f"rag-request-trace-{id(self)}")

    def get_last_trace(self) -> RequestTrace | None:
        """Return diagnostics for the current request context, if completed."""

        return self._traces.get()

    def _record_trace(
        self,
        *,
        question: str,
        chunks: Sequence[RetrievedChunk],
        candidates: Sequence[RetrievedChunk] | None = None,
        generation_output: str | None,
        request_started: float,
        embedding_ms: float = 0.0,
        retrieval_ms: float = 0.0,
        generation_ms: float = 0.0,
        embedding_was_called: bool = False,
        generation_was_called: bool = False,
        embedding_inputs: Sequence[str] | None = None,
        analysis: QueryAnalysis | None = None,
    ) -> None:
        self._traces.set(
            build_request_trace(
                question=question,
                embedder=self._embedder,
                generator=self._generator,
                chunks=chunks,
                candidates=candidates,
                generation_output=generation_output,
                stage_latency=StageLatency(
                    embedding_ms=embedding_ms,
                    retrieval_ms=retrieval_ms,
                    generation_ms=generation_ms,
                    total_ms=round((perf_counter() - request_started) * 1000, 2),
                ),
                embedding_was_called=embedding_was_called,
                generation_was_called=generation_was_called,
                embedding_inputs=embedding_inputs,
                analysis=analysis,
            )
        )

    def index(self, chunks: Sequence[RetrievedChunk]) -> None:
        """Embed and upload chunks while preserving input order."""

        if not chunks:
            return
        vectors = self._embedder.embed([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("embedding count does not match chunk count")
        self._search.index(chunks, vectors)

    async def answer(
        self,
        *,
        question: str,
        top_k: int,
        history: Sequence[ConversationTurn] = (),
    ) -> ChatResult:
        """Retrieve relevant chunks, generate an answer, and verify citations."""

        request_started = perf_counter()
        self._traces.clear()
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        analysis = self._analyze(normalized_question, history)
        if analysis.ambiguous:
            clarification = analysis.clarification or "Please clarify your question."
            result = ChatResult(
                answer=clarification,
                citations=(),
                retrieved_chunks=0,
                status="clarification",
                clarification=clarification,
                rewritten_query=analysis.standalone_query,
                temporal_intent=analysis.temporal_intent.value,
                subqueries=tuple(analysis.subqueries),
            )
            self._record_trace(
                question=normalized_question,
                chunks=(),
                generation_output=None,
                request_started=request_started,
                analysis=analysis,
            )
            return result
        if _GREETING_PATTERN.fullmatch(normalized_question):
            result = ChatResult(answer=GREETING_ANSWER, citations=(), retrieved_chunks=0)
            self._record_trace(
                question=normalized_question,
                chunks=(),
                generation_output=None,
                request_started=request_started,
                analysis=analysis,
            )
            return result
        if self._is_inventory_query(normalized_question):
            retrieval_started = perf_counter()
            documents = await asyncio.to_thread(self._search.inventory)
            retrieval_ms = round((perf_counter() - retrieval_started) * 1000, 2)
            result = self._inventory_result(normalized_question, documents)
            self._record_trace(
                question=normalized_question,
                chunks=(),
                generation_output=None,
                request_started=request_started,
                retrieval_ms=retrieval_ms,
                analysis=analysis,
            )
            return result

        subqueries = tuple(analysis.subqueries) or (analysis.standalone_query,)
        if len(subqueries) > 1 and subqueries[0].casefold() == analysis.standalone_query.casefold():
            subqueries = subqueries[1:]
        embedding_started = perf_counter()
        query_vectors = await asyncio.to_thread(self._embedder.embed, list(subqueries))
        embedding_ms = round((perf_counter() - embedding_started) * 1000, 2)
        if len(query_vectors) != len(subqueries):
            raise ValueError("embedding response count does not match subqueries")

        retrieval_started = perf_counter()
        per_query_candidates = [
            await asyncio.to_thread(
                self._search.search,
                subquery,
                vector,
                top=MAX_CANDIDATES,
            )
            for subquery, vector in zip(subqueries, query_vectors, strict=True)
        ]
        retrieval_ms = round((perf_counter() - retrieval_started) * 1000, 2)
        candidates = fuse_subquery_results(
            per_query_candidates,
            comparison=analysis.temporal_intent is TemporalIntent.COMPARISON,
            limit=MAX_CANDIDATES,
        )
        if not candidates:
            result = ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=0,
            )
            self._record_trace(
                question=normalized_question,
                chunks=(),
                candidates=(),
                generation_output=None,
                request_started=request_started,
                embedding_ms=embedding_ms,
                retrieval_ms=retrieval_ms,
                embedding_was_called=True,
                embedding_inputs=subqueries,
                analysis=analysis,
            )
            return result

        chunks = select_retrieval_context(
            analysis.standalone_query,
            candidates,
            limit=MAX_CONTEXT_CHUNKS,
            historical_intent=analysis.temporal_intent
            in {TemporalIntent.HISTORICAL, TemporalIntent.COMPARISON},
        )

        evidence = self._evidence_gate.assess(
            analysis.standalone_query,
            chunks,
            historical_intent=analysis.temporal_intent
            in {TemporalIntent.HISTORICAL, TemporalIntent.COMPARISON},
        )
        if not evidence.sufficient:
            result = ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=len(chunks),
                rewritten_query=analysis.standalone_query,
                temporal_intent=analysis.temporal_intent.value,
                subqueries=subqueries,
            )
            self._record_trace(
                question=normalized_question,
                chunks=chunks,
                candidates=candidates,
                generation_output=None,
                request_started=request_started,
                embedding_ms=embedding_ms,
                retrieval_ms=retrieval_ms,
                embedding_was_called=True,
                embedding_inputs=subqueries,
                analysis=analysis,
            )
            return result

        generation_started = perf_counter()
        answer = await asyncio.to_thread(
            self._generator.generate, analysis.standalone_query, chunks
        )
        generation_ms = round((perf_counter() - generation_started) * 1000, 2)
        normalized_answer = self._normalize_supported_citation_annotations(answer, chunks)
        citations = (
            self._resolve_citations(normalized_answer, chunks)
            if normalized_answer is not None
            else None
        )
        if not citations:
            result = ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=len(chunks),
                rewritten_query=analysis.standalone_query,
                temporal_intent=analysis.temporal_intent.value,
                subqueries=subqueries,
            )
        else:
            assert normalized_answer is not None
            result = ChatResult(
                answer=normalized_answer,
                citations=citations,
                retrieved_chunks=len(chunks),
                rewritten_query=analysis.standalone_query,
                temporal_intent=analysis.temporal_intent.value,
                subqueries=subqueries,
            )
        self._record_trace(
            question=normalized_question,
            chunks=chunks,
            candidates=candidates,
            generation_output=answer,
            request_started=request_started,
            embedding_ms=embedding_ms,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            embedding_was_called=True,
            generation_was_called=True,
            embedding_inputs=subqueries,
            analysis=analysis,
        )
        return result

    def _analyze(
        self,
        question: str,
        history: Sequence[ConversationTurn],
    ) -> QueryAnalysis:
        try:
            return self._analyzer.analyze(question, history)
        except Exception:
            return DeterministicQueryAnalyzer().analyze(question, history)

    @staticmethod
    def _is_inventory_query(question: str) -> bool:
        return bool(_DOCUMENT_PATTERN.search(question) and _INVENTORY_PATTERN.search(question))

    @classmethod
    def _inventory_result(
        cls,
        question: str,
        documents: Sequence[IndexedDocument],
    ) -> ChatResult:
        ordered_documents = sorted(documents, key=lambda document: document.source_path.casefold())
        department = cls._known_department_in_question(question, ordered_documents)
        if department:
            ordered_documents = [
                document
                for document in ordered_documents
                if cls._department(document.source_path).casefold() == department.casefold()
            ]

        if not ordered_documents:
            scope = f" for {department}" if department else ""
            answer = f"No documents are currently indexed{scope}."
        else:
            count = len(ordered_documents)
            noun = "document" if count == 1 else "documents"
            verb = "is" if count == 1 else "are"
            scope = f" {department}" if department else ""
            summary = f"{count}{scope} {noun} {verb} indexed"
            if _COUNT_PATTERN.search(question):
                answer = f"{summary}."
            else:
                entries = "\n".join(
                    f"- {document.title} - {document.source_path}" for document in ordered_documents
                )
                answer = f"{summary}:\n{entries}"

        return ChatResult(answer=answer, citations=(), retrieved_chunks=0)

    @classmethod
    def _known_department_in_question(
        cls,
        question: str,
        documents: Sequence[IndexedDocument],
    ) -> str | None:
        known_departments = {
            cls._department(document.source_path)
            for document in documents
            if "/" in document.source_path
        }
        departments = sorted(
            known_departments,
            key=len,
            reverse=True,
        )
        lowered_question = question.casefold()
        return next(
            (
                department
                for department in departments
                if re.search(rf"\b{re.escape(department.casefold())}\b", lowered_question)
            ),
            None,
        )

    @staticmethod
    def _department(source_path: str) -> str:
        normalized_path = source_path.replace("\\", "/")
        return PurePosixPath(normalized_path).parent.name

    @staticmethod
    def _normalize_supported_citation_annotations(
        answer: str,
        chunks: Sequence[RetrievedChunk],
    ) -> str | None:
        """Normalize verified model location notes back to exact chunk citations."""

        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        answer = _NESTED_CITATION_PATTERN.sub(r"[\1]", answer)

        def replace(match: re.Match[str]) -> str:
            block = match.group(1).strip()
            if block in chunks_by_id:
                return f"[{block}]"
            grouped_ids = [item.strip() for item in block.split(",")]
            if len(grouped_ids) > 1 and all(item in chunks_by_id for item in grouped_ids):
                return " ".join(f"[{item}]" for item in grouped_ids)
            annotation = re.fullmatch(
                r"(?P<id>[^,\s]+),?\s+(?P<label>rows?|pages?)\s+(?P<values>[0-9,\s]+)",
                block,
                re.IGNORECASE,
            )
            if annotation is None:
                raise ValueError("unsupported citation annotation")
            chunk = chunks_by_id.get(annotation.group("id"))
            if chunk is None:
                raise ValueError("unknown citation ID")
            values = [int(value) for value in re.findall(r"\d+", annotation.group("values"))]
            label = annotation.group("label").casefold()
            if label.startswith("page"):
                if len(values) != 1 or chunk.page_number != values[0]:
                    raise ValueError("citation page does not match retrieved metadata")
            else:
                if chunk.file_type != "xlsx" or not values:
                    raise ValueError("citation row is not supported by retrieved metadata")
                if any(
                    re.search(rf"(?im)^Row:\s*{value}\s*$", chunk.content) is None
                    for value in values
                ):
                    raise ValueError("citation row is not present in retrieved evidence")
            return f"[{chunk.id}]"

        try:
            return _CITATION_BLOCK_PATTERN.sub(replace, answer)
        except ValueError:
            return None

    @staticmethod
    def _resolve_citations(
        answer: str,
        chunks: Sequence[RetrievedChunk],
    ) -> tuple[Citation, ...] | None:
        chunks_by_id: dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            previous = chunks_by_id.get(chunk.id)
            # Duplicate IDs with different provenance make the citation map
            # ambiguous.  Refuse rather than silently selecting one metadata
            # record, which could make a valid-looking citation misleading.
            if previous is not None and _citation_metadata(previous) != _citation_metadata(chunk):
                return None
            chunks_by_id[chunk.id] = chunk

        citation_blocks = _CITATION_BLOCK_PATTERN.findall(answer)
        if not citation_blocks:
            return None
        cited_ids: list[str] = []
        for block in citation_blocks:
            chunk_id = block.strip()
            # Reject all non-ID bracket blocks.  This catches unknown IDs,
            # malformed output, and forged location suffixes consistently.
            if chunk_id not in chunks_by_id:
                return None
            cited_ids.append(chunk_id)
        cited_ids = list(dict.fromkeys(cited_ids))
        unknown_ids = [chunk_id for chunk_id in cited_ids if chunk_id not in chunks_by_id]
        if unknown_ids:
            return None

        return tuple(
            Citation(
                chunk_id=chunk_id,
                source=chunks_by_id[chunk_id].source_path,
                page=chunks_by_id[chunk_id].page_number,
                section=chunks_by_id[chunk_id].section,
            )
            for chunk_id in cited_ids
        )


def _citation_metadata(chunk: RetrievedChunk) -> tuple[object, ...]:
    """Return all provenance fields that a citation could expose."""

    return (
        chunk.title,
        chunk.source_path,
        chunk.page_number,
        chunk.section,
        chunk.sheet_name,
        chunk.table_number,
        chunk.row_number,
    )
