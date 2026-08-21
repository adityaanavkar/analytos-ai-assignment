"""A7 provider-failure safety and query-analysis trace coverage."""

from collections.abc import Sequence
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.rag.models import IndexedDocument, RetrievedChunk
from app.rag.query_analysis import AzureQueryAnalyzer, ConversationTurn
from app.rag.service import RagService


class RecordingEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts = list(texts)
        return [[1.0] for _ in texts]


class FailingEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        raise AssertionError("ambiguous requests must not reach embeddings")


class RecordingSearch:
    def __init__(self, chunk: RetrievedChunk) -> None:
        self.chunk = chunk
        self.queries: list[str] = []

    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        del chunks, vectors

    def search(
        self,
        query: str,
        vector: Sequence[float],
        *,
        top: int,
    ) -> list[RetrievedChunk]:
        del vector, top
        self.queries.append(query)
        return [self.chunk]

    def inventory(self) -> list[IndexedDocument]:
        return []


class RecordingGenerator:
    def __init__(self, chunk_id: str) -> None:
        self.question = ""
        self.chunk_id = chunk_id

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        self.question = question
        return f"Starter is documented [{self.chunk_id}]."


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        id="starter-2025",
        content="Starter was $29 in 2025.",
        title="Pricing 2025",
        source_path="KnowledgeBase/Sales/Pricing2025.pdf",
        page_number=1,
        version="2025",
        is_current=False,
    )


@pytest.mark.asyncio
async def test_malformed_provider_output_falls_back_to_clarification_and_is_traced() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]
    )
    service = RagService(
        FailingEmbedder(),
        RecordingSearch(_chunk()),
        RecordingGenerator("starter-2025"),
        analyzer=AzureQueryAnalyzer(client, deployment="query-analysis"),
    )

    result = await service.answer(question="What is the limit?", top_k=5)

    assert result.clarification == "Which document, plan, policy, or subject do you mean?"
    assert result.retrieved_chunks == 0
    trace = service.get_last_trace()
    assert trace is not None
    assert trace.analysis is not None
    assert trace.analysis.ambiguous is True
    assert trace.analysis.temporal_intent == "unspecified"
    assert trace.analysis.subqueries == ("What is the limit?",)
    assert trace.to_dict()["analysis"]["ambiguous"] is True


@pytest.mark.asyncio
async def test_provider_exception_falls_back_to_bounded_follow_up_rewrite() -> None:
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("provider unavailable")
    embedder = RecordingEmbedder()
    search = RecordingSearch(_chunk())
    generator = RecordingGenerator("starter-2025")
    service = RagService(
        embedder,
        search,
        generator,
        analyzer=AzureQueryAnalyzer(client, deployment="query-analysis"),
    )

    result = await service.answer(
        question="What about Starter?",
        top_k=5,
        history=[
            ConversationTurn(role="user", content="What was the Starter price in 2025?"),
            ConversationTurn(role="assistant", content="It was documented in the price list."),
        ],
    )

    assert result.citations[0].chunk_id == "starter-2025"
    assert search.queries == ["What was the Starter price in 2025? What about Starter?"]
    assert embedder.texts == search.queries
    assert generator.question == search.queries[0]
    trace = service.get_last_trace()
    assert trace is not None
    assert trace.analysis is not None
    assert trace.analysis.resolved_from_context is True
    assert trace.analysis.standalone_query == search.queries[0]
    assert trace.analysis.subqueries == (search.queries[0],)
