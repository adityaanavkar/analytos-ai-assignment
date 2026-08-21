"""Azure AI Search adapter for the frozen vector-only baseline."""

from collections.abc import Sequence
from typing import Any, cast

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.baseline.models import BASELINE_TOP_K
from app.config import Settings
from app.rag.models import RetrievedChunk


class AzureBaselineSearch:
    """Retrieve exactly five nearest chunks without text or semantic search."""

    def __init__(self, client: SearchClient) -> None:
        self._client = client

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        credential: TokenCredential | None = None,
    ) -> AzureBaselineSearch:
        endpoint = settings.azure_search_endpoint
        if not endpoint:
            raise ValueError("AZURE_SEARCH_ENDPOINT is required for the baseline adapter")
        client = SearchClient(
            endpoint=endpoint,
            index_name=settings.azure_search_baseline_index,
            credential=credential or DefaultAzureCredential(),
        )
        return cls(client)

    def search(self, vector: Sequence[float]) -> list[RetrievedChunk]:
        """Run the immutable vector-only Top-5 baseline query."""

        vector_query = VectorizedQuery(
            vector=list(vector),
            k_nearest_neighbors=BASELINE_TOP_K,
            fields="content_vector",
        )
        results = self._client.search(
            search_text=None,
            vector_queries=[vector_query],
            select=["id", "content", "title", "source_path", "page_number", "section"],
            top=BASELINE_TOP_K,
        )
        return [self._to_chunk(cast("dict[str, Any]", result)) for result in results]

    @staticmethod
    def _to_chunk(result: dict[str, Any]) -> RetrievedChunk:
        raw_page = result.get("page_number")
        raw_section = result.get("section")
        raw_score = result.get("@search.score")
        return RetrievedChunk(
            id=str(result["id"]),
            content=str(result["content"]),
            title=str(result["title"]),
            source_path=str(result["source_path"]),
            page_number=int(raw_page) if raw_page is not None else None,
            section=str(raw_section) if raw_section is not None else None,
            score=float(raw_score) if raw_score is not None else None,
        )

    def close(self) -> None:
        self._client.close()
