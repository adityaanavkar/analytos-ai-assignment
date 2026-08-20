"""Tests for the API system endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from app.config import get_settings
from app.main import app, create_app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "enterprise-knowledge-assistant",
        "environment": "development",
    }


@pytest.mark.asyncio
async def test_health_endpoint_reflects_environment(monkeypatch: MonkeyPatch) -> None:
    """Configuration is read from the environment when an app is created."""

    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.get("/health")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["environment"] == "test"
