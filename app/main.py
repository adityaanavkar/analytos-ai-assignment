"""FastAPI entry point for the enterprise knowledge assistant."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings


class HealthResponse(BaseModel):
    """Public health-check response."""

    status: str
    service: str
    environment: str


def create_app() -> FastAPI:
    """Build the API application without contacting external services."""

    settings = get_settings()
    application = FastAPI(
        title="Enterprise Knowledge Assistant",
        version="0.1.0",
        description="Azure AI Search and Azure OpenAI grounded RAG service.",
    )

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="enterprise-knowledge-assistant",
            environment=settings.app_env,
        )

    return application


app = create_app()
