import json
from pathlib import Path

import pytest

from app.rag.models import ChatResult, Citation
from evaluation.runner import evaluate_pipeline, load_frozen_dataset


class FakeService:
    async def answer(self, *, question: str, top_k: int) -> ChatResult:
        assert top_k == 5
        return ChatResult(
            answer=f"Grounded answer to {question}",
            citations=(Citation(chunk_id="chunk-1", source="KnowledgeBase/Test.pdf"),),
            retrieved_chunks=5,
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
    assert set(output["manual_judgment"].values()) == {None}
    json.dumps(pipeline)
