"""Smoke test for the browser chat interface."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_browser_ui_loads() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Enterprise Knowledge Assistant" in response.text
    assert 'id="chat-form"' in response.text
    assert 'id="conversation"' in response.text
    assert 'role="log"' in response.text
    assert 'id="new-chat"' in response.text
    assert 'fetch("/chat"' in response.text


@pytest.mark.asyncio
async def test_browser_ui_guards_json_parsing_and_has_plain_text_error_fallback() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert 'response.headers.get("content-type")' in response.text
    assert 'contentType.includes("application/json")' in response.text
    assert "response.json().catch(() => null)" in response.text
    assert "The server could not complete the request" in response.text


@pytest.mark.asyncio
async def test_browser_ui_supports_safe_multi_turn_messages_and_citations() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert "function appendUserMessage" in response.text
    assert "function appendAssistantMessage" in response.text
    assert "conversation.insertBefore(message, loading)" in response.text
    assert 'className = "citation-details"' in response.text
    assert 'className = "citation-list"' in response.text
    assert "function displayAnswer(payload)" in response.text
    assert "replaceAll(`[${citation.chunk_id}]`, `[${index + 1}]`)" in response.text
    assert '[...new Set(markers)].join(" ")' in response.text
    assert "citationLabel(citation, index + 1)" in response.text
    assert "textContent = renderedAnswer" in response.text
    assert "(${citation.chunk_id})" not in response.text
    assert "innerHTML" not in response.text


@pytest.mark.asyncio
async def test_browser_ui_sends_bounded_history_and_renders_clarifications() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert "const MAX_HISTORY_TURNS = 6" in response.text
    assert "conversationHistory.slice(-MAX_HISTORY_TURNS)" in response.text
    assert "JSON.stringify({ question: submittedQuestion, top_k: 5, history })" in response.text
    assert 'payload.status === "clarification"' in response.text
    assert "conversationHistory = []" in response.text


@pytest.mark.asyncio
async def test_browser_ui_has_keyboard_mobile_and_accessible_states() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert "@media (max-width: 760px)" in response.text
    assert "@media (prefers-reduced-motion: reduce)" in response.text
    assert 'event.key === "Enter"' in response.text
    assert "!event.shiftKey" in response.text
    assert 'role="status"' in response.text
    assert 'role="alert"' in response.text
    assert 'aria-label="Send question"' in response.text
