"""Live-like chat regressions through FastAPI with a fully mocked backend."""

from collections.abc import Mapping

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.main import ChatResponse, create_app


class ScenarioChatService:
    """Deterministic backend for realistic non-document chat inputs."""

    def __init__(self, answers: Mapping[str, str]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []

    async def answer(self, *, question: str, top_k: int) -> ChatResponse:
        self.calls.append((question, top_k))
        return ChatResponse(
            answer=self.answers[question],
            citations=[],
            retrieved_chunks=0,
        )


class FailingChatService:
    """Backend that simulates an unexpected provider failure."""

    async def answer(self, *, question: str, top_k: int) -> ChatResponse:
        raise RuntimeError("secret provider details must not reach the response")


async def _post_chat(service: ScenarioChatService, question: str) -> Response:
    application = create_app(chat_service_factory=lambda: service)
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        return await client.post("/chat", json={"question": question})


@pytest.mark.asyncio
async def test_greeting_is_accepted_and_serialized_without_citations() -> None:
    service = ScenarioChatService({"Hi": "Hello. Ask me a question about the knowledge base."})

    response = await _post_chat(service, "Hi")

    assert response.status_code == 200
    assert service.calls == [("Hi", 5)]
    assert response.json() == {
        "answer": "Hello. Ask me a question about the knowledge base.",
        "citations": [],
        "retrieved_chunks": 0,
    }


@pytest.mark.asyncio
async def test_typo_or_nonsense_is_returned_as_a_safe_no_evidence_answer() -> None:
    service = ScenarioChatService(
        {"whjat": "I could not find supporting information in the knowledge base."}
    )

    response = await _post_chat(service, "whjat")

    assert response.status_code == 200
    assert service.calls == [("whjat", 5)]
    assert response.json()["citations"] == []
    assert response.json()["retrieved_chunks"] == 0
    assert "could not find supporting information" in response.json()["answer"]


@pytest.mark.asyncio
async def test_empty_input_is_rejected_before_the_backend_is_called() -> None:
    service = ScenarioChatService({})

    response = await _post_chat(service, "   ")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "question"
    assert service.calls == []


@pytest.mark.asyncio
async def test_backend_initialization_error_is_sanitized_as_json() -> None:
    def unavailable_backend() -> ScenarioChatService:
        raise RuntimeError("secret provider details must not reach the response")

    application = create_app(chat_service_factory=unavailable_backend)
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"question": "What is the policy?"})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "The chat service is not available."}
    assert "secret provider details" not in response.text


@pytest.mark.asyncio
async def test_backend_answer_error_is_sanitized_as_json() -> None:
    application = create_app(chat_service_factory=FailingChatService)
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.post("/chat", json={"question": "What is the policy?"})

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "The chat service could not complete the request."}
    assert "secret provider details" not in response.text
