import json
from pathlib import Path

import pytest

from app.rag.models import ChatResult, Citation
from app.rag.trace import RequestTrace, StageLatency
from evaluation.runner import evaluate_pipeline, load_frozen_dataset
from evaluation.usage_cost import build_usage_cost_evidence


class FakeService:
    async def answer(self, *, question: str, top_k: int) -> ChatResult:
        assert top_k == 5
        return ChatResult(
            answer=f"Grounded answer to {question}",
            citations=(Citation(chunk_id="chunk-1", source="KnowledgeBase/Test.pdf"),),
            retrieved_chunks=5,
        )

    def get_last_trace(self) -> RequestTrace:
        return RequestTrace(
            question="What is documented?",
            embedding_deployment="embedding-deployment",
            generation_deployment="chat-deployment",
            candidates=(),
            generation_output="Grounded answer",
            stage_latency=StageLatency(1.0, 2.0, 3.0, 6.0),
            usage_cost=build_usage_cost_evidence(
                embedding_inputs=["What is documented?"],
                chat_inputs=["Grounded input"],
                chat_output="Grounded answer",
                embedding_model="text-embedding-3-small",
                chat_model="gpt-4.1-mini",
            ),
        )


def test_core_dataset_is_frozen_and_has_stable_ids() -> None:
    dataset, digest = load_frozen_dataset(Path("evaluation/datasets/core_v1.json"))

    assert len(dataset["cases"]) == 10
    assert [case["id"] for case in dataset["cases"]] == [
        f"CORE-{number:03d}" for number in range(1, 11)
    ]
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_evaluation_captures_full_output_without_inventing_scores() -> None:
    pipeline = await evaluate_pipeline(
        "baseline",
        FakeService(),
        [{"id": "CORE-001", "question": "What is documented?"}],
    )

    output = pipeline["outputs"][0]
    assert output["answer"] == "Grounded answer to What is documented?"
    assert output["citations"][0]["chunk_id"] == "chunk-1"
    assert output["retrieved_chunks"] == 5
    assert output["latency_ms"] >= 0
    assert output["request_trace"]["embedding_deployment"] == "embedding-deployment"
    assert output["request_trace"]["stage_latency"]["retrieval_ms"] == 2.0
    assert output["request_trace"]["usage_cost"]["usage"]["total_tokens"] > 0
    assert set(output["manual_judgment"].values()) == {None}
    json.dumps(pipeline)
