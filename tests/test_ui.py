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
