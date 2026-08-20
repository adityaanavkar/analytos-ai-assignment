"""Direct Azure SDK adapters for the first working RAG path."""

from collections.abc import Sequence
from typing import Any, cast

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

from app.config import Settings
from app.rag.models import IndexedDocument, RetrievedChunk

_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


def _required(value: str | None, environment_name: str) -> str:
    if not value:
        raise ValueError(f"{environment_name} is required for the Azure RAG adapter")
    return value


class AzureOpenAIAdapter:
    """Uses Azure OpenAI for embeddings and grounded chat generation."""

    def __init__(
        self,
        client: AzureOpenAI,
        *,
        embedding_deployment: str,
        chat_deployment: str,
    ) -> None:
        self._client = client
        self._embedding_deployment = embedding_deployment
        self._chat_deployment = chat_deployment

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        credential: TokenCredential | None = None,
    ) -> AzureOpenAIAdapter:
        """Create an Entra-authenticated adapter from environment-backed settings."""

        resolved_credential = credential or DefaultAzureCredential()
        token_provider = get_bearer_token_provider(resolved_credential, _COGNITIVE_SERVICES_SCOPE)
        client = AzureOpenAI(
            azure_endpoint=_required(settings.azure_openai_endpoint, "AZURE_OPENAI_ENDPOINT"),
            azure_ad_token_provider=token_provider,
            api_version="2024-10-21",
        )
        return cls(
            client,
            embedding_deployment=_required(
                settings.azure_openai_embedding_deployment,
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            ),
            chat_deployment=_required(
                settings.azure_openai_chat_deployment,
                "AZURE_OPENAI_CHAT_DEPLOYMENT",
            ),
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self._embedding_deployment,
            input=list(texts),
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        evidence = "\n\n".join(f"[{chunk.id}] {chunk.title}\n{chunk.content}" for chunk in chunks)
        response = self._client.chat.completions.create(
            model=self._chat_deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer only from the supplied evidence. "
                        "Cite every factual claim using the exact chunk ID in square brackets. "
                        "If the evidence is insufficient, say so."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nEvidence:\n{evidence}",
                },
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Azure OpenAI returned an empty answer")
        return content

    def close(self) -> None:
        self._client.close()


class AzureSearchAdapter:
    """Uses one Azure AI Search index for chunk upload and hybrid retrieval."""

    def __init__(self, client: SearchClient) -> None:
        self._client = client

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        credential: TokenCredential | None = None,
    ) -> AzureSearchAdapter:
        """Create an Entra-authenticated improved-index adapter from settings."""

        client = SearchClient(
            endpoint=_required(settings.azure_search_endpoint, "AZURE_SEARCH_ENDPOINT"),
            index_name=settings.azure_search_improved_index,
            credential=credential or DefaultAzureCredential(),
        )
        return cls(client)

    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("vector count does not match chunk count")
        documents = [
            {
                "id": chunk.id,
                "content": chunk.content,
                "title": chunk.title,
                "source_path": chunk.source_path,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "content_vector": list(vector),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        results = self._client.upload_documents(documents=documents)
        failed = [str(result.key or "<unknown>") for result in results if not result.succeeded]
        if failed:
            raise RuntimeError(f"Azure AI Search failed to index: {', '.join(failed)}")

    def search(
        self,
        query: str,
        vector: Sequence[float],
        *,
        top: int,
    ) -> list[RetrievedChunk]:
        vector_query = VectorizedQuery(
            vector=list(vector),
            k_nearest_neighbors=top,
            fields="content_vector",
        )
        results = self._client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=["id", "content", "title", "source_path", "page_number", "section"],
            top=top,
        )
        return [self._to_chunk(cast("dict[str, Any]", result)) for result in results]

    def inventory(self) -> list[IndexedDocument]:
        """Return distinct indexed sources for this assignment-sized index."""

        results = self._client.search(
            search_text="*",
            select=["title", "source_path"],
            top=1000,
        )
        documents_by_path: dict[str, IndexedDocument] = {}
        for raw_result in results:
            result = cast("dict[str, Any]", raw_result)
            source_path = str(result["source_path"]).replace("\\", "/")
            key = source_path.casefold()
            if key not in documents_by_path:
                documents_by_path[key] = IndexedDocument(
                    title=str(result["title"]),
                    source_path=source_path,
                )
        return sorted(
            documents_by_path.values(),
            key=lambda document: document.source_path.casefold(),
        )

    @staticmethod
    def _to_chunk(result: dict[str, Any]) -> RetrievedChunk:
        raw_score = result.get("@search.score")
        raw_page = result.get("page_number")
        return RetrievedChunk(
            id=str(result["id"]),
            content=str(result["content"]),
            title=str(result["title"]),
            source_path=str(result["source_path"]),
            page_number=int(raw_page) if raw_page is not None else None,
            section=str(result["section"]) if result.get("section") is not None else None,
            score=float(raw_score) if raw_score is not None else None,
        )

    def close(self) -> None:
        self._client.close()
