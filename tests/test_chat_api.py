"""Tests for the first chat API vertical slice."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import ChatCitation, ChatResponse, create_app


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
