"""Run the permanent core evaluation against baseline and improved RAG."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.baseline import get_baseline_service
from app.config import get_settings
from app.rag import ChatResult, get_rag_service

DEFAULT_DATASET = Path("evaluation/datasets/core_v1.json")
DEFAULT_RESULTS_ROOT = Path("evaluation/results")
CORE_V1_SHA256 = "9a76a255bd500a6f8a602a633d9c968b7bcaaff89a8b8bf279fa2c6684844f64"


class AnswerService(Protocol):
    """Common async interface implemented by both RAG pipelines."""

    async def answer(self, *, question: str, top_k: int) -> ChatResult: ...


def load_frozen_dataset(path: Path) -> tuple[dict[str, Any], str]:
    """Load and validate the immutable ten-case contract."""

    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    dataset: dict[str, Any] = json.loads(raw)
    cases = dataset.get("cases")
    if dataset.get("frozen") is not True or not isinstance(cases, list) or len(cases) != 10:
        raise ValueError("Evaluation dataset must be frozen and contain exactly 10 cases")
    ids = [case.get("id") for case in cases]
    if ids != [f"CORE-{number:03d}" for number in range(1, 11)]:
        raise ValueError("Evaluation case IDs or order changed")
    if dataset.get("version") == "core-v1" and digest != CORE_V1_SHA256:
        raise ValueError("core-v1 bytes changed after the first recorded run")
    return dataset, digest


async def evaluate_pipeline(
    name: str,
    service: AnswerService,
    cases: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Capture full observable output without assigning subjective scores."""

    outputs: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        try:
            result = await service.answer(question=str(case["question"]), top_k=5)
            error = None
        except Exception as exc:  # noqa: BLE001 - errors are evaluation evidence
            result = None
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        outputs.append(
            {
                "case_id": case["id"],
                "question": case["question"],
                "answer": result.answer if result else None,
                "citations": [
                    {
                        "chunk_id": citation.chunk_id,
                        "source": citation.source,
                        "page": citation.page,
                        "section": citation.section,
                    }
                    for citation in (result.citations if result else ())
                ],
                "retrieved_chunks": result.retrieved_chunks if result else None,
                "latency_ms": latency_ms,
                "error": error,
                "manual_judgment": {
                    "correctness_0_to_4": None,
                    "completeness_0_to_4": None,
                    "grounding_0_to_4": None,
                    "citation_quality_0_to_4": None,
                    "total_0_to_16": None,
                    "judge_notes": None,
                },
            }
        )
    return {"pipeline": name, "outputs": outputs}


def _git_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _metadata(dataset_hash: str) -> dict[str, Any]:
    settings = get_settings()
    return {
        "run_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_revision(),
        "dataset_sha256": dataset_hash,
        "corpus_fingerprint": "ba1733838a948e08093db141458d5b7e29302e9b612b9d2108556c1d53b16313",
        "azure_search_baseline_index": settings.azure_search_baseline_index,
        "azure_search_improved_index": settings.azure_search_improved_index,
        "embedding_deployment": settings.azure_openai_embedding_deployment,
        "generation_deployment": settings.azure_openai_chat_deployment,
        "baseline_retrieval": "vector-only fixed Top 5",
        "improved_retrieval": "hybrid retrieval configured by app.rag",
        "scoring": "Manual only. Four dimensions scored 0-4, maximum 16 per case.",
    }


async def run(pipeline: str, dataset_path: Path) -> dict[str, Any]:
    """Run one or both pipelines against the unchanged cases."""

    dataset, dataset_hash = load_frozen_dataset(dataset_path)
    services: list[tuple[str, AnswerService]] = []
    if pipeline in {"baseline", "both"}:
        services.append(("baseline", get_baseline_service()))
    if pipeline in {"improved", "both"}:
        services.append(("improved", get_rag_service()))
    results = [
        await evaluate_pipeline(name, service, dataset["cases"])
        for name, service in services
    ]
    return {
        "dataset": {
            "id": dataset["dataset_id"],
            "version": dataset["version"],
            "case_count": len(dataset["cases"]),
        },
        "metadata": _metadata(dataset_hash),
        "pipelines": results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", choices=("baseline", "improved", "both"), default="both")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run evaluation and save its complete unscored evidence artifact."""

    args = _build_parser().parse_args(argv)
    result = asyncio.run(run(args.pipeline, args.dataset))
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or DEFAULT_RESULTS_ROOT / f"core_v1_{args.pipeline}_{timestamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Saved complete unscored evaluation: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
