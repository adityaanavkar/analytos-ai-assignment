# Azure Enterprise RAG Assignment - Implementation Tracker

This file is the execution source of truth for the assignment. Update it in the
same change that advances or completes an action. The repository must always
show what was done, how it was done, why the approach was chosen, and the
evidence that supports the status.

## Status and update contract

- `Pending`: work has not started.
- `In progress`: implementation has started, but one or more acceptance checks
  have not passed.
- `Blocked`: an external dependency prevents progress; record the blocker,
  attempted workarounds, owner, and next retry condition.
- `Complete`: every acceptance check passed and the completion journal contains
  concrete What, How, Why, Evidence, and Deviations/follow-up entries.

Rules for every action:

1. Change the master checklist and that action's journal in the same commit.
2. Before starting, set the action to `In progress` and note the intended work.
3. Before completing, record:
   - **What:** exact behavior, components, or infrastructure delivered.
   - **How:** important implementation details, commands, and integration path.
   - **Why:** engineering reasoning and meaningful alternatives rejected.
   - **Evidence:** tests, measured metrics, deployment output, or screenshots.
   - **Deviations/follow-up:** limitations or `None`.
4. Do not mark an action complete based only on code existing; its stated
   acceptance checks must pass.
5. Never use illustrative numbers as results. Label unmeasured values as
   `TBD`, preserve raw outputs, and date any price assumptions.
6. Never commit credentials, access keys, tokens, `.env`, user queries, or
   sensitive document content in logs.
7. Preserve the frozen baseline index, configuration, dataset, and result files
   before implementing or measuring the improved pipeline.
8. Record failures and deviations instead of silently omitting them.

## Master checklist

| ID | Action | Status | Depends on | Acceptance evidence |
|---|---|---|---|---|
| P0 | Local environment and source-document validation | Complete | - | Python environment validated; 11 source documents parsed |
| A1 | Repository, tracker, and local application foundation | Complete | P0 | Clean Git state, health endpoint, configuration tests, Ruff, mypy, pytest |
| A2 | Azure preflight, budget guardrails, and reproducible infrastructure | Complete | A1 | Active subscription, capability/quota report, reviewed Bicep deployment outputs |
| A3 | Canonical document/chunk schema and metadata policy | In progress | A1 | Typed schemas and version/ACL/provenance tests |
| A4 | PDF, DOCX, XLSX, and Blob ingestion | In progress | A2, A3 | All 11 files ingested without silent loss; dry-run and idempotency evidence |
| A5 | Frozen baseline vector-only RAG | Pending | A2, A4 | Separate baseline index/config and immutable baseline results |
| A6 | Structure-aware chunking and hybrid retrieval | In progress | A5 | Improved index plus wrong-chunk and multi-section retrieval evidence |
| A7 | Query analysis, decomposition, and conversation context | Pending | A6 | Ambiguous, comparison, historical, and follow-up tests |
| A8 | Evidence sufficiency, grounded generation, and citation validation | In progress | A6, A7 | No-answer, grounding, and citation-tampering tests |
| A9 | Retrieval-time department access control | Pending | A6 | Positive and negative cross-department security tests |
| A10 | Chat API and lightweight browser UI | In progress | A7, A8, A9 | Working local demo with citations, clarification, ACLs, and diagnostics |
| A11 | Frozen evaluation set and baseline/improved comparison | Pending | A5-A10 | Reproducible raw and summary reports with measured metrics |
| A12 | Observability, latency, tokens, and cost reporting | Pending | A10, A11 | Stage traces, safe telemetry, and dated cost calculation |
| A13 | Production architecture and six problem-solving answers | Pending | A2-A12 | Exported diagram and reviewer-ready technical documentation |
| A14 | Final verification, video script, and submission package | Pending | A13 | Clean verification run and complete submission checklist |

## First end-to-end MVP checkpoint

- **Completed:** 2026-08-21.
- **What:** Deployed the first live Azure stack, extracted and chunked `KnowledgeBase/Finance/ExpensePolicy.pdf`, created the improved Search index, uploaded four embedded chunks, and exposed a browser-backed `POST /chat` flow.
- **How:** The application uses `DefaultAzureCredential`, `text-embedding-3-small`, hybrid Azure AI Search retrieval, and `gpt-4.1-mini` grounded generation with application-validated chunk citations.
- **Why:** A thin working vertical slice validates the riskiest integration boundaries early and provides a demonstrable base for incremental ingestion, retrieval, security, and evaluation improvements.
- **Evidence:** The live API returned HTTP 200 for an Expense Policy question, retrieved four chunks, answered the 30-day and 60-day submission rules correctly, and cited the source PDF page 1.
- **Deviations/follow-up:** The MVP currently covers one PDF, one improved index, fixed-size chunks, and a minimal UI.
- **Deviations/follow-up:** It does not yet satisfy the full A3-A10 acceptance criteria for all formats, metadata, baseline comparison, query analysis, ACLs, evidence calibration, diagnostics, or evaluation.

## Fixed implementation decisions

- Use Python, FastAPI, Pydantic, and direct Azure/OpenAI SDKs rather than
  LangChain so retrieval and failure behavior remain inspectable.
- Run the API and simple web UI locally. Deploy only the minimum live Azure
  services: Azure OpenAI, Azure AI Search, Blob Storage, and optional
  Application Insights. Show enterprise-only hosting/networking in the diagram.
- Provision Azure resources through parameterized Bicep, not manual Portal
  creation. Use one assignment resource group with consistent tags.
- Use `DefaultAzureCredential`/Entra ID by default. Allow API keys only as a
  documented local fallback loaded from an ignored `.env` file.
- Prefer a free Azure AI Search tier. Do not create a paid Search service
  without explicit user approval after displaying the estimated monthly cost.
- Prefer `centralindia`, then `eastus2`, then `swedencentral`, choosing the first
  allowed region with model capacity. Record the actual region and model SKUs.
- Prefer `gpt-5-mini`, then `gpt-4.1-mini`, for generation and
  `text-embedding-3-small` at 1,536 dimensions for embeddings, subject to the
  subscription's current availability and quota.
- Keep baseline and improved indexes/configurations separate. The baseline uses
  fixed-size chunks, vector-only Top-5 retrieval, no rewrite, no semantic
  reranking, no version preference, and no evidence gate.
- The improved pipeline uses heading-aware 300-600 token chunks, an 800-token
  hard maximum, about 80 tokens of within-section overlap, table-header
  repetition, hybrid BM25/vector Top-20 candidates, optional semantic
  reranking, deduplication, source diversity, and up to six generation chunks.
- Apply department/group ACL and version filters inside Azure AI Search, never
  after retrieval. Explicit historical questions may access historical versions;
  otherwise current documents are preferred.
- Require the model to cite supplied chunk IDs. Resolve IDs to source metadata
  in application code and reject unknown or fabricated IDs.
- Calibrate retrieval/evidence thresholds only on a training/calibration split;
  never tune them on the held-out comparison set.
- Use deterministic metrics plus an Azure OpenAI rubric judge. Store judge
  scores and explanations so results can be audited.

## Action specifications and journals

### P0 - Local environment and source-document validation

Acceptance checks:

- The virtual environment imports all runtime and development dependencies.
- `pip check` reports no dependency conflicts.
- Every supplied PDF, DOCX, and XLSX file can be opened by its parser.

Journal:

- **Completed:** 2026-08-20
- **What:** Created `.venv`, separated runtime/development requirements, and
  added ignore rules for credentials, environments, caches, and artifacts.
- **How:** Installed direct Azure, FastAPI, parsing, telemetry, resilience,
  testing, linting, and typing dependencies from `requirements*.txt`; ran import
  and parser smoke checks.
- **Why:** Direct SDKs keep the implementation observable and defensible while a
  separate dev dependency file keeps the runtime surface smaller.
- **Evidence:** `pip check` found no broken requirements; core imports passed;
  the smoke test opened 7 PDFs, 3 DOCX files, and 1 XLSX workbook.
- **Deviations/follow-up:** Python 3.14 is newer than many production runtimes;
  verify all checks continuously and document a supported deployment runtime.

### A1 - Repository, tracker, and local application foundation

Acceptance checks:

- Repository is on `main`, has an `origin`, and contains no tracked secrets or
  virtual-environment files.
- Typed settings load safe defaults and fail clearly when live Azure mode lacks
  required configuration.
- `GET /health` works without Azure credentials and exposes no secrets.
- Ruff, mypy, and pytest pass; README local commands are executable.

Journal:

- **Completed:** 2026-08-20
- **What:** Added the execution tracker, beginner-oriented README, safe
  environment template, shared quality configuration, typed application
  settings, FastAPI application factory, dependency packages, infrastructure
  and architecture placeholders, and foundation tests.
- **How:** The health endpoint is deliberately independent of Azure. Pydantic
  settings use safe local defaults and a model-level validation guard that
  lists every missing variable when `AZURE_ENABLED=true`. Tests call the ASGI
  app directly through HTTPX, including environment loading and valid/invalid
  live-Azure configurations.
- **Why:** A cloud-independent health path makes local development and incident
  diagnosis reliable. Fail-fast configuration prevents late, provider-specific
  SDK errors, while direct SDK boundaries keep later RAG stages inspectable.
- **Evidence:** The repository is on `main` with `origin` configured; the Azure
  subscription is Enabled and default. Ruff and Ruff formatting passed, strict
  mypy found no issues, all 5 tests passed, application coverage was 100%
  (44/44 statements), and `pip check` reported no broken requirements.
- **Deviations/follow-up:** Python 3.14 works locally; select and document an
  Azure-supported deployment runtime if the app is later hosted. Cloud resource
  providers remain unregistered and will be handled explicitly in A2.

### A2 - Azure preflight, budget guardrails, and reproducible infrastructure

Acceptance checks:

- Record the selected subscription, allowed region, provider registration,
  Search tier availability, model availability/quota, and a cost guardrail.
- Bicep validates and deploys idempotently with sanitized outputs for resource
  names/endpoints/deployments; no secret is written to Git.
- The deployment creates only approved demo resources and documents teardown.

Journal:

- **Completed:** 2026-08-21.
- **What:** Registered required providers and deployed Azure OpenAI, Azure AI Search Basic, Blob Storage, Log Analytics, Application Insights, model deployments, and least-privilege data-plane role assignments through Bicep.
- **How:** Subscription-specific discovery verified model availability and quota before deployment, Bicep `what-if` previewed 13 intended changes, and sanitized deployment outputs supplied only service names and endpoints to the ignored local `.env`.
- **Why:** Reproducible infrastructure and Entra authentication avoid manual drift and committed secrets while keeping the local MVP easy to run.
- **Evidence:** Deployment `analytos-ai-demo` succeeded in `rg-analytos-ai-demo`; the live embedding call returned 1,536 dimensions and the live grounded chat smoke test returned the required citation.
- **Deviations/follow-up:** East US 2 lacked new Search Basic capacity, so Search was placed in Central India while Azure OpenAI and monitoring remained in East US 2.
- **Deviations/follow-up:** The first OpenAI deployment attempt exposed concurrent child-deployment conflicts and the first Search definition combined incompatible authentication properties; the Bicep was corrected and redeployed incrementally.

### A3 - Canonical document/chunk schema and metadata policy

Acceptance checks:

- The schema includes deterministic IDs, content/content hash, vector, title,
  source path, file type, department, document type, version/effective dates,
  `is_current`, page/section/sheet/table context, and allowed groups.
- Tests prove deterministic IDs, serialization, provenance, ACL metadata, and
  current-versus-historical classification.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A4 - PDF, DOCX, XLSX, and Blob ingestion

Acceptance checks:

- Parsers preserve PDF page, DOCX heading/table, and XLSX sheet/row/header
  provenance, with explicit warnings for empty or unsupported content.
- Local-folder and Blob inputs use the same pipeline; dry-run previews chunks
  before cloud mutation.
- Embeddings are batched with bounded concurrency, retry/backoff, partial-error
  reporting, and content-hash idempotency.
- All 11 supplied files ingest successfully and a second run creates no
  unintended duplicates.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A5 - Frozen baseline vector-only RAG

Acceptance checks:

- A separate baseline index uses fixed-size chunks, vector-only Top-5 retrieval,
  the chosen embedding model, and the same generation model/evaluation set as
  the improved pipeline.
- Answers include basic citations, while rewrite, version policy, semantic
  reranking, decomposition, and evidence gating remain disabled.
- Raw retrieval/generation outputs, latency, tokens, approximate cost, config,
  code revision, and timestamp are saved before A6 begins.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A6 - Structure-aware chunking and hybrid retrieval

Acceptance checks:

- Heading-aware chunks and table row groups retain provenance and obey the
  fixed token/overlap policy.
- Hybrid keyword/vector retrieval gathers Top-20 candidates, optionally applies
  Azure semantic ranking, deduplicates, diversifies, and returns up to six.
- Tests demonstrate recovery from a correct-document/wrong-chunk failure and
  retrieval of all evidence needed across multiple sections/documents.
- Semantic-ranker unavailability has a tested hybrid-only fallback.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A7 - Query analysis, decomposition, and conversation context

Acceptance checks:

- Structured analysis returns standalone query, ambiguity result, clarification,
  temporal intent, and at most three subqueries with schema validation/fallback.
- Ambiguous questions clarify unless relevant recent context resolves them.
- Comparisons/multi-document questions retrieve each subquery then fuse results;
  follow-ups use a standalone rewrite instead of raw full-history retrieval.
- Explicit historical intent bypasses the default current-version preference.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A8 - Evidence sufficiency, grounded generation, and citation validation

Acceptance checks:

- Generation receives only authorized retrieved chunks and must cite their IDs.
- Application code rejects unknown IDs and maps valid IDs to title plus
  page/section/sheet metadata.
- A configurable evidence gate, calibrated on training cases, refuses unsupported
  questions with an explicit insufficient-evidence response.
- Tests cover missing information, conflicting sources, malformed output,
  citation tampering, and a valid-looking but incorrectly mapped citation.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A9 - Retrieval-time department access control

Acceptance checks:

- Local demo requires `X-User-Groups` and converts validated group values to a
  safely escaped Azure AI Search filter before retrieval.
- Tests prove permitted access and prove an Engineering-only user receives zero
  HR chunks, including through rewrites, subqueries, and debug output.
- Documentation states that production derives groups from validated Entra ID
  claims and never trusts a caller-supplied header.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A10 - Chat API and lightweight browser UI

Acceptance checks:

- `GET /health`, `POST /api/chat`, and `POST /api/evaluate` have documented,
  typed request/response schemas and predictable error responses.
- Chat accepts question, bounded history, pipeline mode, and debug flag; it
  returns status, answer/clarification, rewritten query, citations, confidence,
  timings, and optional safe retrieval diagnostics.
- UI demonstrates group selection, conversation, clarification, citations,
  latency, baseline/improved mode, and errors without exposing secrets.
- Azure dependency failures, timeouts, malformed input, and empty retrieval are
  handled and covered by tests.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A11 - Frozen evaluation set and baseline/improved comparison

Acceptance checks:

- Freeze 20 cases: 6 straightforward, 4 cross-section/multi-document, 3
  current-versus-historical, 2 unanswered, 2 ambiguous, and 3 follow-ups.
- Each case records expected answer behavior, documents/sections, difficulty,
  groups, conversation context, and answerability.
- Run identical cases against baseline and improved pipelines. Measure Hit@5,
  Recall@5, MRR, chunk relevance/precision, correctness, groundedness, citation
  precision, refusal quality, hallucination rate, latency, tokens, and cost.
- Preserve raw outputs and judge explanations; report regressions as well as
  improvements and never claim improvement without measured evidence.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A12 - Observability, latency, tokens, and cost reporting

Acceptance checks:

- Structured timings/traces cover analysis, embedding, search, reranking,
  evidence checking, generation, and citation validation with a correlation ID.
- Application Insights receives telemetry when configured and local logging is a
  tested fallback.
- Logs exclude document text, secrets, group claims, and full user queries by
  default; token counts and dated model-price assumptions drive cost estimates.
- A documented workflow diagnoses a 3-to-12-second latency regression by stage.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A13 - Production architecture and six problem-solving answers

Acceptance checks:

- Mermaid source plus exported SVG/PNG show ingestion, Blob Storage, AI Search,
  Azure OpenAI, API/app layer, Entra ID, managed identity, Key Vault, monitoring,
  private endpoints, scaling, data isolation, and cost controls.
- Documentation distinguishes the minimal live demo from production and explains
  why Azure AI Search and hybrid retrieval were chosen.
- README answers all six required topics: poor Top-5 relevance, 3-to-12-second
  latency, growth from 10,000 to 5 million documents, departmental security,
  cost spike diagnosis, and wrong answers with valid-looking citations.
- Scaling discussion covers partitioning/capacity, asynchronous incremental
  ingestion, index/version migration, retries/DLQ, caching, and observability.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

### A14 - Final verification, video script, and submission package

Acceptance checks:

- Ruff, mypy, unit tests, mocked integration tests, live Azure smoke tests,
  security tests, ingestion idempotency, and a clean-environment setup pass.
- Dependency versions are reproducible; secret scanning and Git status are clean.
- Five-minute script covers architecture, Azure choices, working chatbot, one or
  two baseline failures, diagnosis, improvements, evaluation, and production
  hardening.
- Submission checklist contains GitHub link, architecture diagram, evaluation
  results, mandatory video link, latest resume, recipients, and exact subject;
  sending the email remains a manual user action.
- Teardown instructions identify billable demo resources and are verified before
  the project is handed off.

Journal: **Status:** Pending. **What/How/Why/Evidence/Deviations:** TBD.

## Failure-scenario traceability

| Assignment scenario | Implementation | Required proof |
|---|---|---|
| Correct document, wrong chunk | A5 baseline; A6 structure-aware hybrid retrieval/reranking | Same question fails or ranks poorly in baseline and improves measurably |
| Information across sections/documents | A6 retrieval fusion; A7 decomposition | Every required source is retrieved and cited |
| Similar/conflicting document versions | A3 metadata; A7 temporal intent/version filter | Current query selects current version; explicit historical query still works |
| Missing information/hallucination | A8 evidence gate | Unsupported questions refuse and cite nothing fabricated |
| Ambiguous query | A7 ambiguity policy | Clarification is returned unless recent context resolves the subject |
| Conversational context | A7 standalone rewrite | Follow-ups resolve correctly without irrelevant full-history retrieval |
| Department isolation | A9 retrieval-time ACL | Engineering-only identity cannot retrieve HR content |
| Wrong answer with valid-looking citation | A8 validation; A12 stage traces | Tampered/unknown IDs fail and debugging evidence identifies the failing stage |

## Deliverable exit criteria

- **GitHub repository:** application, ingestion, retrieval, Azure integrations,
  tests, evaluation scripts/data/results, configuration sample, and README.
- **Architecture diagram:** production Azure design in editable source and an
  image format suitable for submission.
- **Evaluation results:** reproducible baseline-versus-improved report with raw
  evidence, measured metrics, configuration, timestamp, and honest limitations.
- **Demo/presentation:** candidate-owned five-minute recording using the prepared
  script and showing the working system plus at least one diagnosed improvement.
- **Submission package:** repository link, diagram, video link, results, resume,
  recipients `santosh.thota@analytos.ai` and `ashok.suthar@analytos.ai`, and
  subject `Senior AI Engineer - Azure RAG Task - Aditya Anavkar`.
