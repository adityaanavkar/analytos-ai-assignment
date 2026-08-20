"""FastAPI entry point for the enterprise knowledge assistant."""

from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Annotated, Protocol, cast

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints

from app.config import get_settings

STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


class HealthResponse(BaseModel):
    """Public health-check response."""

    status: str
    service: str
    environment: str


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatRequest(BaseModel):
    """Validated input for one retrieval-augmented answer."""

    question: Annotated[NonEmptyText, StringConstraints(max_length=2_000)]
    top_k: int = Field(default=5, ge=1, le=20)


class ChatCitation(BaseModel):
    """Source location supporting an answer."""

    chunk_id: NonEmptyText
    source: NonEmptyText
    page: int | None = Field(default=None, ge=1)
    section: str | None = None


class ChatResponse(BaseModel):
    """Grounded answer returned by the chat service."""

    answer: NonEmptyText
    citations: list[ChatCitation] = Field(default_factory=list)
    retrieved_chunks: int = Field(ge=0)


class ChatService(Protocol):
    """Boundary implemented by the RAG orchestration service."""

    async def answer(self, *, question: str, top_k: int) -> ChatResponse:
        """Return an answer grounded in retrieved document chunks."""


ChatServiceFactory = Callable[[], ChatService]


def _load_chat_service() -> ChatService:
    """Load the RAG service lazily so health checks stay cloud independent."""

    try:
        rag_module = import_module("app.rag")
    except ModuleNotFoundError as exc:
        if exc.name != "app.rag":
            raise
        raise RuntimeError("The RAG service is not installed yet.") from exc

    factory = getattr(rag_module, "get_rag_service", None) or getattr(
        rag_module, "build_chat_service", None
    )
    if factory is None or not callable(factory):
        raise RuntimeError("app.rag must expose get_rag_service() or build_chat_service().")

    return cast(ChatService, factory())


def create_app(chat_service_factory: ChatServiceFactory = _load_chat_service) -> FastAPI:
    """Build the API application without contacting external services."""

    settings = get_settings()
    application = FastAPI(
        title="Enterprise Knowledge Assistant",
        version="0.1.0",
        description="Azure AI Search and Azure OpenAI grounded RAG service.",
    )

    @application.get("/", response_class=FileResponse, include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIRECTORY / "index.html")

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="enterprise-knowledge-assistant",
            environment=settings.app_env,
        )

    def resolve_chat_service() -> ChatService:
        try:
            return chat_service_factory()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The chat service is not available.",
            ) from exc

    @application.post("/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(
        request: ChatRequest,
        chat_service: Annotated[ChatService, Depends(resolve_chat_service)],
    ) -> ChatResponse:
        return await chat_service.answer(question=request.question, top_k=request.top_k)

    return application


app = create_app()
