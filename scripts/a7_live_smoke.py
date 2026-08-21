"""Run focused live Azure acceptance checks for A7 query analysis."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.rag import get_rag_service
from app.rag.query_analysis import ConversationTurn

CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "A7-ambiguous",
        "question": "What is the limit?",
        "history": (),
    },
    {
        "id": "A7-follow-up",
        "question": "What about Starter?",
        "history": (
            ConversationTurn(role="user", content="What is the Starter price in 2026?"),
            ConversationTurn(
                role="assistant",
                content="The 2026 Starter price is available in the pricing document.",
            ),
        ),
    },
    {
        "id": "A7-historical",
        "question": "What was the Starter price in 2025?",
        "history": (),
    },
    {
        "id": "A7-comparison",
        "question": "Compare the Starter price in 2025 and 2026.",
        "history": (),
    },
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", dest="case_id", choices=[case["id"] for case in CASES])
    return parser


async def _run(case_id: str | None = None) -> dict[str, Any]:
    service = get_rag_service()
    outputs: list[dict[str, Any]] = []
    for case in CASES:
        if case_id and case["id"] != case_id:
            continue
        result = await service.answer(
            question=str(case["question"]),
            top_k=5,
            history=case["history"],
        )
        trace = service.get_last_trace()
        trace_data = trace.to_dict() if trace else {}
        outputs.append(
            {
                "case_id": case["id"],
                "question": case["question"],
                "answer": result.answer,
                "status": result.status,
                "clarification": result.clarification,
                "rewritten_query": result.rewritten_query,
                "temporal_intent": result.temporal_intent,
                "subqueries": list(result.subqueries),
                "retrieved_chunks": result.retrieved_chunks,
                "citations": [
                    {
                        "chunk_id": citation.chunk_id,
                        "source": citation.source,
                        "page": citation.page,
                        "section": citation.section,
                    }
                    for citation in result.citations
                ],
                "trace_analysis": trace_data.get("analysis"),
                "trace_candidates": trace_data.get("candidates"),
                "selected_context": trace_data.get("selected_context"),
                "stage_latency": trace_data.get("stage_latency"),
            }
        )
    return {"suite": "A7 live smoke", "outputs": outputs}


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = json.dumps(asyncio.run(_run(args.case_id)), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Saved A7 live smoke evidence: {args.output}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
