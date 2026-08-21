"""Focused tests for the minimal RAG orchestration path."""

from collections.abc import Sequence

import pytest

from app.rag.models import IndexedDocument, RetrievedChunk
from app.rag.query_analysis import ConversationTurn, QueryAnalysis, TemporalIntent
from app.rag.service import GREETING_ANSWER, INSUFFICIENT_EVIDENCE_ANSWER, RagService


class FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class UnexpectedEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("this deterministic request must not call Azure OpenAI")


class FakeSearch:
    def __init__(
        self,
        chunks: list[RetrievedChunk],
        documents: list[IndexedDocument] | None = None,
    ) -> None:
        self.chunks = chunks
        self.documents = documents or []
        self.indexed: tuple[Sequence[RetrievedChunk], Sequence[Sequence[float]]] | None = None
        self.last_top: int | None = None

    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        self.indexed = (chunks, vectors)

    def search(
        self,
        query: str,
        vector: Sequence[float],
        *,
        top: int,
    ) -> list[RetrievedChunk]:
        self.last_top = top
        return self.chunks[:top]

    def inventory(self) -> list[IndexedDocument]:
        return self.documents


class FakeGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        return self.answer


class RecordingGenerator:
    def __init__(self) -> None:
        self.chunks: tuple[RetrievedChunk, ...] = ()

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        del question
        self.chunks = tuple(chunks)
        return f"Grounded result [{chunks[0].id}]."


class FixedAnalyzer:
    def __init__(self, analysis: QueryAnalysis) -> None:
        self.analysis = analysis
        self.calls: list[tuple[str, tuple[ConversationTurn, ...]]] = []

    def analyze(
        self,
        question: str,
        history: Sequence[ConversationTurn] = (),
    ) -> QueryAnalysis:
        self.calls.append((question, tuple(history)))
        return self.analysis


class RecordingSearch(FakeSearch):
    def __init__(self, by_query: dict[str, list[RetrievedChunk]]) -> None:
        super().__init__([])
        self.by_query = by_query
        self.queries: list[str] = []

    def search(
        self,
        query: str,
        vector: Sequence[float],
        *,
        top: int,
    ) -> list[RetrievedChunk]:
        del vector
        self.queries.append(query)
        return self.by_query.get(query, [])[:top]


class RecordingQuestionGenerator(RecordingGenerator):
    def __init__(self, answer: str) -> None:
        super().__init__()
        self.question = ""
        self.answer = answer

    def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        self.question = question
        self.chunks = tuple(chunks)
        return self.answer


def _chunk(chunk_id: str = "pricing-2026-1") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        content="Enterprise support is included.",
        title="Pricing 2026",
        source_path="KnowledgeBase/Pricing2026.pdf",
        page_number=2,
    )


@pytest.mark.asyncio
async def test_answer_returns_only_verified_citations() -> None:
    chunk = _chunk()
    service = RagService(
        FakeEmbedder(),
        FakeSearch([chunk]),
        FakeGenerator("Support is included [pricing-2026-1]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == "Support is included [pricing-2026-1]."
    assert result.citations[0].chunk_id == chunk.id
    assert result.citations[0].page == 2
    assert result.retrieved_chunks == 1


@pytest.mark.asyncio
async def test_answer_collapses_nested_verified_citation_brackets() -> None:
    chunk = _chunk()
    service = RagService(
        FakeEmbedder(),
        FakeSearch([chunk]),
        FakeGenerator("Support is included [[pricing-2026-1]]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == "Support is included [pricing-2026-1]."
    assert [citation.chunk_id for citation in result.citations] == [chunk.id]


@pytest.mark.asyncio
async def test_answer_normalizes_grouped_verified_citation_ids() -> None:
    first = _chunk("pricing-1")
    second = RetrievedChunk(
        id="pricing-2",
        content="The annual term discount is 15%.",
        title="Discounts",
        source_path="KnowledgeBase/Sales/Discounts.xlsx",
        sheet_name="Term Discounts",
        row_number=6,
    )
    service = RagService(
        FakeEmbedder(),
        FakeSearch([first, second]),
        FakeGenerator("Support and discounts apply [pricing-1, pricing-2]."),
    )

    result = await service.answer(question="What support and discounts apply?", top_k=5)

    assert result.answer == "Support and discounts apply [pricing-1] [pricing-2]."
    assert [citation.chunk_id for citation in result.citations] == ["pricing-1", "pricing-2"]


@pytest.mark.asyncio
async def test_ambiguous_analysis_clarifies_without_provider_calls() -> None:
    analyzer = FixedAnalyzer(
        QueryAnalysis(
            standalone_query="What is the policy?",
            ambiguous=True,
            clarification="Which policy do you mean?",
        )
    )
    service = RagService(
        UnexpectedEmbedder(),
        FakeSearch([]),
        FakeGenerator("must not generate"),
        analyzer=analyzer,
    )

    result = await service.answer(question="What is the policy?", top_k=5)

    assert result.answer == "Which policy do you mean?"
    assert result.status == "clarification"
    assert result.clarification == "Which policy do you mean?"
    assert result.retrieved_chunks == 0


@pytest.mark.asyncio
async def test_comparison_retrieves_each_subquery_and_generates_standalone_query() -> None:
    current = RetrievedChunk(
        id="current",
        content="2026 price is $32.",
        title="Pricing 2026",
        source_path="KnowledgeBase/Sales/Pricing2026.pdf",
        score=0.9,
        department="Sales",
        document_type="rate_card",
        version="2026",
        is_current=True,
    )
    historical = RetrievedChunk(
        id="historical",
        content="2025 price was $29.",
        title="Pricing 2025",
        source_path="KnowledgeBase/Sales/Pricing2025.pdf",
        score=0.8,
        department="Sales",
        document_type="rate_card",
        version="2025",
        is_current=False,
    )
    analysis = QueryAnalysis(
        standalone_query="Compare Starter pricing in 2025 and 2026.",
        temporal_intent=TemporalIntent.COMPARISON,
        subqueries=["Starter pricing in 2025", "Starter pricing in 2026"],
    )
    analyzer = FixedAnalyzer(analysis)
    search = RecordingSearch(
        {
            "Starter pricing in 2025": [historical],
            "Starter pricing in 2026": [current],
        }
    )
    generator = RecordingQuestionGenerator("2025 was $29 and 2026 is $32 [historical] [current].")
    service = RagService(FakeEmbedder(), search, generator, analyzer=analyzer)

    result = await service.answer(
        question="Compare pricing.",
        top_k=5,
        history=[ConversationTurn(role="user", content="Pricing")],
    )

    assert search.queries == ["Starter pricing in 2025", "Starter pricing in 2026"]
    assert generator.question == analysis.standalone_query
    assert {citation.chunk_id for citation in result.citations} == {"historical", "current"}
    assert result.temporal_intent == "comparison"
    assert result.subqueries == ("Starter pricing in 2025", "Starter pricing in 2026")
    assert analyzer.calls[0][1][0].content == "Pricing"


@pytest.mark.asyncio
async def test_comparison_context_keeps_exact_price_evidence_from_each_version() -> None:
    historical = RetrievedChunk(
        id="starter-2025-exact",
        content="Starter price: $29 per seat per month in 2025.",
        title="Pricing 2025",
        source_path="KnowledgeBase/Sales/Pricing2025.pdf",
        score=0.91,
        department="Sales",
        document_type="rate_card",
        version="2025",
        is_current=False,
    )
    current = RetrievedChunk(
        id="starter-2026-exact",
        content="Starter price: $32 per seat per month in 2026.",
        title="Pricing 2026",
        source_path="KnowledgeBase/Sales/Pricing2026.pdf",
        score=0.92,
        department="Sales",
        document_type="rate_card",
        version="2026",
        is_current=True,
    )
    analysis = QueryAnalysis(
        standalone_query="Compare the exact Starter price in 2025 and 2026.",
        temporal_intent=TemporalIntent.COMPARISON,
        subqueries=["Starter price in 2025", "Starter price in 2026"],
    )
    search = RecordingSearch(
        {
            "Starter price in 2025": [historical],
            "Starter price in 2026": [current],
        }
    )
    generator = RecordingQuestionGenerator(
        "2025 was $29 [starter-2025-exact]; 2026 is $32 [starter-2026-exact]."
    )
    service = RagService(FakeEmbedder(), search, generator, analyzer=FixedAnalyzer(analysis))

    result = await service.answer(question="Compare Starter prices.", top_k=5)

    selected = {chunk.id: chunk.content for chunk in generator.chunks}
    assert selected == {
        "starter-2025-exact": "Starter price: $29 per seat per month in 2025.",
        "starter-2026-exact": "Starter price: $32 per seat per month in 2026.",
    }
    assert {citation.chunk_id for citation in result.citations} == {
        "starter-2025-exact",
        "starter-2026-exact",
    }


@pytest.mark.asyncio
async def test_follow_up_uses_bounded_context_rewrite_for_search_and_generation() -> None:
    prior_question = "What is the Starter price in 2026?"
    follow_up = "What about Starter?"
    history = [
        ConversationTurn(role="user", content="Older context must be ignored."),
        ConversationTurn(role="assistant", content="Older answer must be ignored."),
        ConversationTurn(role="user", content="Earlier unrelated question."),
        ConversationTurn(role="assistant", content="Earlier unrelated answer."),
        ConversationTurn(role="user", content="Another unrelated question."),
        ConversationTurn(role="assistant", content="Another unrelated answer."),
        ConversationTurn(role="user", content=prior_question),
        ConversationTurn(role="assistant", content="The 2026 price is $32 [starter-2026]."),
    ]
    chunk = RetrievedChunk(
        id="starter-2026",
        content="Starter costs $32 in 2026.",
        title="Pricing 2026",
        source_path="KnowledgeBase/Sales/Pricing2026.pdf",
        version="2026",
        is_current=True,
    )
    search = RecordingSearch(
        {f"{prior_question} {follow_up}": [chunk]},
    )
    generator = RecordingQuestionGenerator("Starter costs $32 [starter-2026].")
    service = RagService(FakeEmbedder(), search, generator)

    result = await service.answer(question=follow_up, top_k=5, history=history)

    standalone = f"{prior_question} {follow_up}"
    assert search.queries == [standalone]
    assert generator.question == standalone
    assert "Older context must be ignored" not in generator.question
    assert result.rewritten_query == standalone
    assert result.temporal_intent == "historical"
    assert result.citations[0].chunk_id == chunk.id


@pytest.mark.asyncio
async def test_explicit_historical_intent_keeps_prior_version_during_context_selection() -> None:
    current = RetrievedChunk(
        id="starter-2026",
        content="Starter costs $32 in 2026.",
        title="Pricing 2026",
        source_path="KnowledgeBase/Sales/Pricing2026.pdf",
        department="Sales",
        document_type="rate_card",
        version="2026",
        is_current=True,
    )
    historical = RetrievedChunk(
        id="starter-2025",
        content="Starter cost $29 in 2025.",
        title="Pricing 2025",
        source_path="KnowledgeBase/Sales/Pricing2025.pdf",
        department="Sales",
        document_type="rate_card",
        version="2025",
        is_current=False,
    )
    question = "What was the Starter price in 2025?"
    search = RecordingSearch({question: [current, historical]})
    generator = RecordingQuestionGenerator("Starter cost $29 in 2025 [starter-2025].")
    service = RagService(FakeEmbedder(), search, generator)

    result = await service.answer(question=question, top_k=5)

    assert search.queries == [question]
    assert generator.question == question
    assert {chunk.id for chunk in generator.chunks} == {"starter-2026", "starter-2025"}
    assert "starter-2025" in {chunk.id for chunk in generator.chunks}
    assert result.temporal_intent == "historical"
    assert [citation.chunk_id for citation in result.citations] == ["starter-2025"]


@pytest.mark.asyncio
async def test_answer_replaces_a_fabricated_citation_with_safe_refusal() -> None:
    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("Support is included [invented-chunk]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 1


@pytest.mark.asyncio
async def test_answer_rejects_a_forged_location_suffix_in_a_citation() -> None:
    """A model-provided row/page suffix must not override chunk provenance."""

    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("Support is included [pricing-2026-1, row 10]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()


@pytest.mark.asyncio
async def test_answer_rejects_a_valid_id_mixed_with_malformed_citation() -> None:
    """One valid citation must not make another unsupported claim look grounded."""

    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("Support is included [pricing-2026-1] [pricing-2026-1, page 99]."),
    )

    result = await service.answer(question="Is support included?", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()


def test_citation_resolution_rejects_ambiguous_duplicate_chunk_id_provenance() -> None:
    """A duplicate ID with different metadata must never map to an arbitrary source."""

    first = _chunk("duplicate")
    second = RetrievedChunk(
        id="duplicate",
        content=first.content,
        title="A different title",
        source_path="KnowledgeBase/Other.pdf",
        page_number=99,
    )
    assert (
        RagService._resolve_citations("Support is included [duplicate].", (first, second)) is None
    )


@pytest.mark.asyncio
async def test_answer_normalizes_verified_xlsx_row_annotations() -> None:
    chunk = RetrievedChunk(
        id="discount-group",
        content="Row: 4\nList price=$65\n\nRow: 21\nCombined discount=35%",
        title="Discounts",
        source_path="KnowledgeBase/Sales/Discounts.xlsx",
        file_type="xlsx",
        sheet_name="Volume Discounts",
    )
    service = RagService(
        FakeEmbedder(),
        FakeSearch([chunk]),
        FakeGenerator("The final discount is 35% [discount-group rows 4, 21]."),
    )

    result = await service.answer(question="What is the final discount?", top_k=5)

    assert result.answer == "The final discount is 35% [discount-group]."
    assert [citation.chunk_id for citation in result.citations] == ["discount-group"]


@pytest.mark.asyncio
async def test_answer_refuses_without_calling_generation_when_search_is_empty() -> None:
    service = RagService(FakeEmbedder(), FakeSearch([]), FakeGenerator("must not be returned"))

    result = await service.answer(question="What is the vacation policy?", top_k=5)

    assert result.citations == ()
    assert result.retrieved_chunks == 0
    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER


@pytest.mark.asyncio
async def test_hi_returns_a_deterministic_greeting_without_azure_calls() -> None:
    service = RagService(UnexpectedEmbedder(), FakeSearch([]), FakeGenerator("unused"))

    result = await service.answer(question="Hi", top_k=5)

    assert result.answer == GREETING_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 0


@pytest.mark.asyncio
async def test_nonsense_with_uncited_generation_returns_safe_refusal() -> None:
    service = RagService(
        FakeEmbedder(),
        FakeSearch([_chunk()]),
        FakeGenerator("I cannot answer that from the supplied evidence."),
    )

    result = await service.answer(question="whjat", top_k=5)

    assert result.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == ()
    assert result.retrieved_chunks == 1


@pytest.mark.asyncio
async def test_document_inventory_returns_exact_count_and_sorted_sources() -> None:
    documents = [
        IndexedDocument("Travel Policy", "Finance/TravelPolicy.docx"),
        IndexedDocument("Benefits", "HR/Benefits.pdf"),
    ]
    service = RagService(UnexpectedEmbedder(), FakeSearch([], documents), FakeGenerator("unused"))

    result = await service.answer(
        question="what all documents are available in RAG",
        top_k=5,
    )

    assert result.answer == (
        "2 documents are indexed:\n"
        "- Travel Policy - Finance/TravelPolicy.docx\n"
        "- Benefits - HR/Benefits.pdf"
    )
    assert result.citations == ()
    assert result.retrieved_chunks == 0


@pytest.mark.asyncio
async def test_document_count_query_returns_only_the_exact_count() -> None:
    documents = [
        IndexedDocument("Travel Policy", "Finance/TravelPolicy.docx"),
        IndexedDocument("Benefits", "HR/Benefits.pdf"),
    ]
    service = RagService(UnexpectedEmbedder(), FakeSearch([], documents), FakeGenerator("unused"))

    result = await service.answer(question="total number of documents available", top_k=5)

    assert result.answer == "2 documents are indexed."
    assert result.citations == ()
    assert result.retrieved_chunks == 0


@pytest.mark.asyncio
async def test_document_inventory_filters_only_a_department_found_in_paths() -> None:
    documents = [
        IndexedDocument("Travel Policy", "KnowledgeBase/Finance/TravelPolicy.docx"),
        IndexedDocument("Expense Policy", "KnowledgeBase/Finance/ExpensePolicy.pdf"),
        IndexedDocument("Benefits", "KnowledgeBase/HR/Benefits.pdf"),
    ]
    service = RagService(FakeEmbedder(), FakeSearch([], documents), FakeGenerator("unused"))

    result = await service.answer(question="which Finance documents are available", top_k=5)

    assert result.answer == (
        "2 Finance documents are indexed:\n"
        "- Expense Policy - KnowledgeBase/Finance/ExpensePolicy.pdf\n"
        "- Travel Policy - KnowledgeBase/Finance/TravelPolicy.docx"
    )


@pytest.mark.asyncio
async def test_document_inventory_handles_an_empty_index() -> None:
    service = RagService(FakeEmbedder(), FakeSearch([]), FakeGenerator("unused"))

    result = await service.answer(question="total number of documents available", top_k=5)

    assert result.answer == "No documents are currently indexed."
    assert result.citations == ()
    assert result.retrieved_chunks == 0


def test_index_embeds_and_passes_aligned_vectors_to_search() -> None:
    chunks = [_chunk("one"), _chunk("two")]
    search = FakeSearch([])
    service = RagService(FakeEmbedder(), search, FakeGenerator("unused"))

    service.index(chunks)

    expected_vectors = [[float(len(chunk.content))] for chunk in chunks]
    assert search.indexed == (chunks, expected_vectors)


@pytest.mark.asyncio
async def test_improved_service_records_20_candidates_but_generates_from_at_most_6() -> None:
    candidates = [
        RetrievedChunk(
            id=f"chunk-{index}",
            content=f"Evidence for topic {index}",
            title=f"Document {index}",
            source_path=f"KnowledgeBase/Test/Document{index}.pdf",
        )
        for index in range(20)
    ]
    search = FakeSearch(candidates)
    generator = RecordingGenerator()
    service = RagService(FakeEmbedder(), search, generator)

    result = await service.answer(question="What evidence is available?", top_k=5)
    trace = service.get_last_trace()

    assert search.last_top == 20
    assert 1 <= len(generator.chunks) <= 6
    assert result.retrieved_chunks == len(generator.chunks)
    assert trace is not None
    assert len(trace.candidates) == 20
    assert [item.id for item in trace.selected_context] == [chunk.id for chunk in generator.chunks]
