"""Orchestration for a simple retrieve-then-generate RAG request."""

import asyncio
import re
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Protocol

from app.rag.models import ChatResult, Citation, IndexedDocument, RetrievedChunk

_CITATION_PATTERN = re.compile(r"\[([^\[\]\s]+)\]")
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
        if _GREETING_PATTERN.fullmatch(normalized_question):
            return ChatResult(answer=GREETING_ANSWER, citations=(), retrieved_chunks=0)
        if self._is_inventory_query(normalized_question):
            documents = await asyncio.to_thread(self._search.inventory)
            return self._inventory_result(normalized_question, documents)

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
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=0,
            )

        answer = await asyncio.to_thread(self._generator.generate, normalized_question, chunks)
        citations = self._resolve_citations(answer, chunks)
        if not citations:
            return ChatResult(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=(),
                retrieved_chunks=len(chunks),
            )
        return ChatResult(answer=answer, citations=citations, retrieved_chunks=len(chunks))

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
    def _resolve_citations(
        answer: str,
        chunks: Sequence[RetrievedChunk],
    ) -> tuple[Citation, ...] | None:
        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        cited_ids = list(dict.fromkeys(_CITATION_PATTERN.findall(answer)))
        unknown_ids = [chunk_id for chunk_id in cited_ids if chunk_id not in chunks_by_id]
        if unknown_ids:
            return None
        if not cited_ids:
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
