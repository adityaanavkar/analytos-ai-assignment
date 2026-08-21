"""Tests for the first chat API vertical slice."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import ChatCitation, ChatResponse, create_app
from app.rag.models import ChatResult
from app.rag.query_analysis import ConversationTurn


class StubChatService:
    """Deterministic replacement for Azure-backed RAG in API tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def answer(self, *, question: str, top_k: int) -> ChatResponse:
        self.calls.append((question, top_k))
        return ChatResponse(
            answer="Enterprise customers can cancel with 30 days notice.",
            citations=[
                ChatCitation(
                    chunk_id="policy-001-chunk-03",
                    source="CancellationPolicy.pdf",
                    page=2,
                    section="Enterprise",
                )
            ],
            retrieved_chunks=1,
        )


class FailingChatService:
    """Provider failure containing a detail that must not reach API clients."""

    async def answer(self, *, question: str, top_k: int) -> ChatResponse:
        raise ConnectionError(f"private provider detail for {question} at top_k={top_k}")


class HistoryAwareChatService:
    """Service double for the optional A7 conversation contract."""

    def __init__(self) -> None:
        self.history: list[ConversationTurn] = []

    async def answer(
        self,
        *,
        question: str,
        top_k: int,
        history: list[ConversationTurn] | tuple[ConversationTurn, ...] = (),
    ) -> ChatResponse:
        del question, top_k
        self.history = list(history)
        return ChatResponse(
            answer="Which plan do you mean?",
            citations=[],
            retrieved_chunks=0,
            status="clarification",
            clarification="Which plan do you mean?",
            rewritten_query="",
            temporal_intent="unspecified",
            subqueries=[],
        )


class RagClarificationService:
    """RAG-shaped service double proving clarification status reaches the API."""

    async def answer(
        self,
        *,
        question: str,
        top_k: int,
        history: list[ConversationTurn] | tuple[ConversationTurn, ...] = (),
    ) -> ChatResult:
        del question, top_k, history
        return ChatResult(
            answer="Which policy do you mean?",
            citations=(),
            retrieved_chunks=0,
            status="clarification",
            clarification="Which policy do you mean?",
        )


@pytest.mark.asyncio
async def test_chat_endpoint_returns_grounded_answer() -> None:
    service = StubChatService()
    application = create_app(chat_service_factory=lambda: service)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/chat",
            json={"question": "  What is the Enterprise cancellation policy?  ", "top_k": 3},
        )

    assert response.status_code == 200
    assert service.calls == [("What is the Enterprise cancellation policy?", 3)]
    assert response.json() == {
        "answer": "Enterprise customers can cancel with 30 days notice.",
        "citations": [
            {
                "chunk_id": "policy-001-chunk-03",
                "source": "CancellationPolicy.pdf",
                "page": 2,
                "section": "Enterprise",
            }
        ],
        "retrieved_chunks": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"question": "   "}, "question"),
        ({"question": "Valid question", "top_k": 0}, "top_k"),
        ({"question": "Valid question", "top_k": 21}, "top_k"),
    ],
)
async def test_chat_endpoint_rejects_invalid_input(payload: dict[str, object], field: str) -> None:
    service = StubChatService()
    application = create_app(chat_service_factory=lambda: service)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post("/chat", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field
    assert service.calls == []


@pytest.mark.asyncio
async def test_chat_endpoint_reports_unavailable_service() -> None:
    def unavailable_factory() -> StubChatService:
        raise RuntimeError("Azure configuration is missing")

    application = create_app(chat_service_factory=unavailable_factory)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post("/chat", json={"question": "What is the policy?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "The chat service is not available."}


@pytest.mark.asyncio
async def test_chat_endpoint_forwards_bounded_typed_history_and_a7_fields() -> None:
    service = HistoryAwareChatService()
    application = create_app(chat_service_factory=lambda: service)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/chat",
            json={
                "question": "What about Standard?",
                "history": [
                    {"role": "user", "content": "What is the Enterprise policy?"},
                    {"role": "assistant", "content": "Enterprise allows cancellation."},
                ],
            },
        )

    assert response.status_code == 200
    assert [(turn.role, turn.content) for turn in service.history] == [
        ("user", "What is the Enterprise policy?"),
        ("assistant", "Enterprise allows cancellation."),
    ]
    assert response.json()["status"] == "clarification"
    assert response.json()["clarification"] == "Which plan do you mean?"


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_history_over_six_turns() -> None:
    service = HistoryAwareChatService()
    application = create_app(chat_service_factory=lambda: service)
    history = [{"role": "user", "content": f"Question {index}"} for index in range(7)]

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post("/chat", json={"question": "Next", "history": history})

    assert response.status_code == 422
    assert service.history == []


@pytest.mark.asyncio
async def test_chat_endpoint_serializes_rag_clarification_status() -> None:
    application = create_app(chat_service_factory=RagClarificationService)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post("/chat", json={"question": "What is the limit?"})

    assert response.status_code == 200
    assert response.json()["status"] == "clarification"
    assert response.json()["clarification"] == "Which policy do you mean?"


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["Hi", "whjat"])
async def test_chat_endpoint_sanitizes_unexpected_rag_failure(question: str) -> None:
    application = create_app(chat_service_factory=FailingChatService)

    async with AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"question": question})

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "The chat service could not complete the request."}
    assert "private provider detail" not in response.text
