# Permanent RAG evaluation protocol

`core_v1.json` is the frozen ten-case regression suite for every version from this milestone onward.

Do not edit or replace its cases after the first recorded run.

The runner enforces SHA-256 `9a76a255bd500a6f8a602a633d9c968b7bcaaff89a8b8bf279fa2c6684844f64` and fails if the core-v1 bytes change.

Run both pipelines with the following command.

```powershell
.\.venv\Scripts\python.exe -m evaluation.runner --pipeline both
```

The result JSON preserves every question, full answer, citation, retrieved-chunk count, latency, configuration identifier, dataset hash, corpus fingerprint, commit, timestamp, and an empty manual-judgment form.

The evaluator must inspect each answer against the expected facts and sources, then score correctness, completeness, grounding, and citation quality from 0 to 4 each.

The maximum score is 16 per case and 160 per pipeline.

Scores must never be generated automatically from keyword matching or filled without reading the complete answer.

Every completed RAG version must copy its full outputs, individual scores, rationale, aggregate score, and candid failure analysis into `VERSIONS.md`.

Historical versions that were not run against these exact bytes must be labeled `Not evaluated on core-v1` rather than assigned reconstructed scores.
