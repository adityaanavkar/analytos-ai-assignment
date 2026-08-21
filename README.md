# Analytos.ai Senior AI Engineer Assignment

This repository is the working solution for the **Senior AI Engineer technical
assignment**. The goal is to build an enterprise knowledge assistant that can
answer questions from the supplied company documents and show where each answer
came from.

In plain language, the finished system will:

1. Read the PDF, Word, and Excel files in `KnowledgeBase/`.
2. Split their content into searchable sections while keeping source details.
3. Store those sections in Azure AI Search.
4. Find the most relevant sections when a user asks a question.
5. Ask Azure OpenAI to answer using only the retrieved evidence.
6. Return citations and refuse unsupported answers.

The implementation intentionally compares a simple baseline RAG pipeline with
an improved pipeline so that quality gains can be measured rather than assumed.

## Current status

The first live end-to-end version is running.

- Azure OpenAI, Azure AI Search Basic, Blob Storage, and monitoring are deployed through Bicep.
- All 11 supplied PDF, DOCX, and XLSX documents are indexed as 186 deterministic chunks.
- PDF page, Word heading/table, and Excel sheet/row/header provenance is preserved for citations.
- The FastAPI service and browser UI answer questions through hybrid retrieval and grounded generation.
- Document list, exact count, and department inventory questions use Search metadata instead of model inference.
- Greetings, unsupported questions, citation validation, and JSON error handling have regression coverage.
- A separate 53-chunk vector-only baseline index and permanent ten-case live evaluation are now reproducible.
- Typed query analysis now supports clarification, six-turn bounded history, standalone follow-up rewriting, explicit historical intent, and multi-year comparison decomposition.
- The current quality suite contains 180 passing tests plus Ruff and strict mypy checks.

A6 retrieval quality, A7 query analysis, and A8 evidence safeguards are complete, with the accepted improved pipeline scoring 154/160 against the frozen ten cases.

Retrieval-time access control, the broader 20-case evaluation, and the final video and submission package remain to be completed.

The presentation-ready [production Azure RAG architecture](architecture/production-azure-rag.png) is available with an [editable SVG](architecture/production-azure-rag.svg), [Mermaid source](architecture/production-azure-rag.mmd), and a concise [presentation sequence](architecture/production-architecture.md).

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the live checklist,
acceptance evidence, and engineering decision journal. That tracker must be
updated whenever an action is completed, including what was done, how it was
verified, and why the approach was chosen.

See [VERSIONS.md](VERSIONS.md) for the chronological record of what each working version achieved, how it was verified, what behaved poorly, and what the next version should address.

## Beginner setup

These commands use PowerShell on Windows. Start from the repository folder:

```powershell
cd C:\Aditya\Prep\analotcs
```

### 1. Create and activate the virtual environment

The environment already exists on the original development machine. If you are
setting up a fresh clone, create it first:

```powershell
python -m venv .venv
```

Activate it each time you open a new PowerShell terminal:

```powershell
.\.venv\Scripts\Activate.ps1
```

When activation works, the terminal prompt begins with `(.venv)`.

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes both the application libraries and the tools
used for tests, linting, and type checking.

### 3. Create local configuration

Copy the safe example file:

```powershell
Copy-Item .env.example .env
```

Authenticate the Azure CLI and confirm the intended subscription:

```powershell
az login --use-device-code
az account set --subscription "Azure subscription 1"
az account show --output table
```

The health endpoint works without Azure values.
Live ingestion and chat require the deployed service endpoints in `.env` plus an authenticated Azure CLI session.
Do not commit `.env`, API keys, access tokens, or connection strings because Git is configured to ignore them.

## Run the current application

With the virtual environment active, start the API:

```powershell
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> for the browser assistant.
Open <http://127.0.0.1:8000/health> for the health response:

```json
{
  "status": "ok",
  "service": "enterprise-knowledge-assistant",
  "environment": "development"
}
```

FastAPI's interactive API documentation is available at
<http://127.0.0.1:8000/docs>. Stop the server with `Ctrl+C`.

## Prepare or upload all documents

Preview every parser and chunk count without contacting Azure:

```powershell
python -m scripts.ingest_all
```

Reconcile the dedicated Azure Search index only after reviewing `.env` and the dry run:

```powershell
python -m scripts.ingest_all --upload
```

The upload uses deterministic IDs, batches embeddings, upserts the full corpus, and removes stale chunks only from the dedicated assignment index.

## Run tests and quality checks

Run these commands from the repository root while the virtual environment is
active:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app ingestion scripts tests
python -m pip check
```

The suite currently checks all three real document formats, complete-corpus discovery, inventory behavior, RAG orchestration, Azure adapter boundaries, chat error handling, and the browser/API contract without making live Azure calls.

## Current demo and production target

The high-level request flow is:

```text
PDF / DOCX / XLSX documents
          |
          v
Parse, clean, and split content with source metadata
          |
          v
Create embeddings and index content in Azure AI Search
          |
          v
User question -> analyze intent/history -> retrieve and fuse evidence
          |
          v
Azure OpenAI generates a grounded answer
          |
          v
FastAPI returns the answer, validated citations, and diagnostics
```

The baseline uses fixed 120-word chunks with 20-word overlap and vector-only fixed Top-5 retrieval in a separate Azure Search index.

The current improved version uses structure-aware chunks, hybrid keyword/vector retrieval, query decomposition, relevance-first context selection, and evidence safeguards.

It scores 154/160 compared with the frozen baseline's 140/160 on the unchanged core-v1 cases.

Version intent and query rewriting are implemented, while retrieval-time department access control and broader evaluation remain planned work rather than current claims.

The current demo runs FastAPI and the browser UI locally while using deployed Azure OpenAI, Azure AI Search, Blob Storage, Application Insights, and Log Analytics services.

The proposed production target adds Azure Front Door and WAF, Microsoft Entra application authentication, Azure App Service, Functions-based ingestion, managed identity, Key Vault, private endpoints, autoscaling, and retrieval-time department enforcement.

Use these reviewer-facing architecture artifacts:

- [Presentation PNG](architecture/production-azure-rag.png)
- [Editable SVG](architecture/production-azure-rag.svg)
- [Mermaid source](architecture/production-azure-rag.mmd)
- [Architecture explanation](architecture/production-architecture.md)
- [Spoken presentation talk track](architecture/diagram-presentation-talk-track.md)

## Architecture decisions

### Why Azure AI Search

Azure AI Search provides keyword retrieval, vector similarity, semantic ranking, metadata filtering, managed scaling, and Azure identity integration in one retrieval service.

It also supports applying an `allowed_groups` filter during retrieval, which is safer than retrieving sensitive text and filtering it afterward.

### Why hybrid retrieval

Vector retrieval handles semantic similarity and paraphrased questions.

Keyword retrieval preserves exact policy names, prices, years, identifiers, URLs, and spreadsheet values that embeddings can rank imprecisely.

The improved pipeline combines both candidate sources, optionally uses semantic ranking, fuses the results, and selects a small relevance-first evidence pack.

### Why the application validates citations

The language model is permitted to reference only chunk identifiers supplied in its evidence.

The Python application rejects unknown, malformed, forged, or ambiguously mapped identifiers and resolves accepted identifiers to human-readable source metadata.

This makes citation validity an application-owned control instead of trusting model-generated source labels.

## Evaluation results

The frozen `core-v1` dataset contains ten unchanged cases covering inventory, cross-document questions, spreadsheets, document versions, unsupported questions, and citations.

Every answer was manually reviewed against expected facts and expected sources across correctness, completeness, grounding, and citation quality, with four points available per dimension.

| Measurement | Frozen baseline | Accepted improved v0.7 |
|---|---:|---:|
| Manual score | 140/160 (87.5%) | 154/160 (96.25%) |
| Correctness average | 3.4/4 | 4.0/4 |
| Completeness average | 3.3/4 | 3.9/4 |
| Grounding average | 3.8/4 | 3.9/4 |
| Citation-quality average | 3.5/4 | 3.6/4 |
| Source Hit@5 on eight answerable retrieval cases | 100% | 100% |
| Mean expected-source Recall@5 | 100% | 100% |
| Mean expected-source Precision@5 | 87.5% | 90.0% |
| Mean live latency | 3,927.51 ms | 3,650.23 ms |
| Observed p95 latency | 6,596.61 ms | 6,061.73 ms |

The retrieval metrics are source-level measurements over the eight answerable, non-inventory cases with live candidate traces.

They do not claim semantic claim-level entailment or replace the manual answer review.

The accepted improved run estimated 16,018 total tokens and approximately USD 0.00770582 across ten requests using the dated assumptions in `evaluation/pricing/azure_openai_assumptions_v1.json`.

These token and cost figures are deterministic engineering estimates rather than an Azure billing quote.

The most important remaining weakness is CORE-008, where the values were correct but one citation referenced a general pricing overview instead of the most precise supporting chunk.

Evaluation evidence:

- [Evaluation protocol](evaluation/README.md)
- [Frozen dataset](evaluation/datasets/core_v1.json)
- [Frozen baseline and v0.6 raw comparison](evaluation/results/core_v1_baseline_vs_improved_v0_6.json)
- [Frozen baseline manual judgment](evaluation/results/core_v1_baseline_vs_improved_v0_6_judgment.json)
- [Accepted improved v0.7 raw output and traces](evaluation/results/core_v1_improved_v0_7_accepted_unscored.json)
- [Accepted improved v0.7 manual judgment](evaluation/results/core_v1_improved_v0_7_accepted_judgment.json)
- [Chronological version record](VERSIONS.md)

The accepted evaluation is a strong frozen ten-case regression suite, but it does not claim to be the broader twenty-case production evaluation described in the implementation plan.

## Security design

Production users authenticate through Microsoft Entra ID, and the API derives department and group membership from the validated token.

The browser must never be trusted to choose its own department or access scope.

Every indexed chunk carries `department` and `allowed_groups` metadata alongside its provenance and version fields.

The production API converts trusted group claims into an Azure AI Search filter that executes before ranking and before any content reaches Azure OpenAI.

The same access filter must apply to the original query, every rewritten or decomposed query, diagnostics, caching, and citation resolution.

Missing or invalid claims must fail closed.

Managed identity, least-privilege RBAC, Key Vault, private endpoints, encrypted storage, redacted telemetry, and audit logs protect the surrounding services.

The schema already preserves `allowed_groups`, but retrieval-time ACL enforcement and positive and negative cross-department tests remain an explicitly documented production gap.

## Known limitations and production improvements

- The application UI and FastAPI API currently run locally rather than on Azure App Service.
- Retrieval-time department enforcement is designed and represented in metadata but is not yet implemented end to end.
- Claim-level semantic entailment is not yet used to prove that every cited chunk supports every generated claim.
- The accepted evaluation contains ten frozen cases rather than the planned broader twenty-case suite.
- Responses are not streamed.
- The deployed Search and OpenAI services are in different regions, which should be revisited for production latency and data-residency requirements.
- Production should add private endpoints, VNet integration, managed application identity, Key Vault integration, deployment slots, autoscaling, queue-based ingestion, retry and dead-letter handling, and Azure Monitor alerts.

## Suggested demonstration

Start the application and open <http://127.0.0.1:8000>.

Use these questions during the video:

1. `What is the expense submission deadline and receipt threshold?`
2. `What are the company password requirements?`
3. `What is the CEO's favorite color?`

The first two demonstrate grounded retrieval and readable citations.

The third demonstrates the deterministic insufficient-evidence refusal without fabricated citations.

Use the [architecture talk track](architecture/diagram-presentation-talk-track.md) while presenting the production diagram.

## Architecture and problem-solving answers

### 1. Five chunks are retrieved, but only one is relevant

I would reproduce the exact query and inspect the rewritten query, all candidate chunks, lexical and vector scores, semantic rank, metadata, selected context, raw generation output, and final citations.

I would measure Hit@5, Recall@5, reciprocal rank, source or chunk precision, and citation coverage on a frozen labeled dataset before changing the system.

Common causes include fixed chunks separating headings from answers, missing table headers, weak handling of exact values, obsolete versions, missing filters, and an overly broad Top-K.

The baseline here uses fixed 120-word chunks and vector-only Top-5 retrieval.

The improved pipeline uses structure-aware chunks, a broader hybrid candidate pool, semantic ranking when available, deterministic fusion, version-aware metadata, and bounded relevance-first context selection.

Every adjustment is rerun against the unchanged evaluation cases so an apparent fix cannot silently damage another category.

### 2. Latency increases from three seconds to twelve seconds

I would compare p50 and p95 latency by correlation ID across query analysis, embeddings, Azure AI Search, semantic ranking, context selection, generation, and citation validation.

The request traces in this project preserve stage timings so the slow component can be identified before reducing quality.

Slow embeddings suggest deployment, quota, networking, or unnecessary repeated work.

Slow Search suggests replica pressure, partition pressure, semantic-ranking latency, complex filters, or retries.

Slow generation suggests excessive context, excessive output, throttling, or an unsuitable model.

Mitigations include embedding reuse, bounded context and output, streaming, access-aware caching, timeouts, retry backoff, circuit breakers, and autoscaling.

Any cache key must include the normalized query, access scope, index version, and prompt version to prevent stale or cross-department responses.

### 3. Growth from 10,000 to 5 million documents

At 10,000 documents, a single Blob corpus and Azure AI Search service with measured replicas and partitions is operationally simple.

Ingestion should still use deterministic identifiers, content hashes, idempotent updates, batching, and stale-chunk cleanup.

At 5 million documents, uploads should emit events into a queue, and scalable Functions or container workers should parse, chunk, embed, and index with checkpoints, bounded concurrency, retries, and a dead-letter queue.

I would size Search partitions for index and vector capacity and replicas for query throughput, then measure vector memory, compression, filter performance, and semantic-ranking cost.

Versioned indexes and aliases enable blue-green reindexing and safe cutovers.

Sharding by tenant, region, department, or time should be introduced only when scale, regulatory isolation, or measured query behavior requires it.

For multi-region availability, the required document partitions can be replicated behind a routing layer while keeping data-residency boundaries explicit.

### 4. HR documents must never be retrieved for Engineering users

Users authenticate through Microsoft Entra ID, and the API derives groups from the validated token rather than a browser-supplied value.

Each chunk contains normalized `allowed_groups` metadata.

The API translates the authenticated groups into an Azure AI Search membership filter and applies it before ranking and before evidence is sent to Azure OpenAI.

The filter must be applied to every decomposed query, version query, cache lookup, diagnostic response, and citation resolution path.

Missing or invalid claims fail closed, and automated negative tests prove that an Engineering-only identity receives zero HR chunks.

For stronger tenant or regulatory isolation, separate indexes or services can supplement metadata filtering.

### 5. Azure OpenAI cost suddenly increases

I would compare Azure Cost Management and application telemetry by model deployment, operation, user, ingestion job, token category, request count, retry count, and time period.

Likely causes include repeated ingestion, duplicate embeddings, retry storms, larger prompts, excessive retrieved context, longer answers, model changes, traffic spikes, or poor cache hit rates.

The main controls are bounded context and output, the smallest model that satisfies evaluation quality, content-hash embedding reuse, batched embeddings, idempotent ingestion, access-aware caching, rate limits, quotas, and Azure budget alerts.

Semantic ranking should be paid for only where it produces a measured quality improvement.

Every cost optimization must rerun the frozen evaluation so savings do not increase hallucinations or reduce citation quality.

### 6. A wrong answer has a valid-looking citation

I would reproduce the exact user identity, query, conversation history, index version, model deployment, and prompt version.

I would inspect the pipeline in order: query analysis, rewritten or decomposed queries, candidates and scores, metadata filters, selected context, exact prompt, raw model output, citation parsing, provenance mapping, and final rendering.

This separates retrieval failures from ranking, context selection, generation, or citation-mapping failures.

A citation identifier can be valid while the cited text does not support the specific claim, so identifier validation alone is insufficient.

The production correction should add claim-level entailment checks, conflict and version detection, stronger reranking, tighter evidence selection, and abstention when support is incomplete.

The reproduced case must be added to the permanent regression suite.

This implementation already rejects unknown, malformed, forged, and ambiguously mapped identifiers, while semantic claim-to-citation verification remains a documented hardening item.

## Azure account and cost safety

The local health endpoint and tests do not create Azure resources or consume Azure credits.

The current Azure OpenAI, Azure AI Search, Blob Storage, Application Insights, and Log Analytics resources are defined reproducibly in Bicep and have been deployed to the dedicated assignment resource group.

Before any deployment:

- Confirm the active subscription with `az account show --output table`.
- Review the Bicep resources, region, service tiers, and expected cost.
- Prefer free or minimal tiers where they satisfy the assignment.
- Never place credentials in source files or Git history.
- Delete temporary cloud resources after the assignment when they are no
  longer required.

Being logged in with `az login` does not itself spend credits. Cost begins only
when billable resources are deployed or used.

## Repository guide

- `app/` - FastAPI application and runtime configuration.
- `KnowledgeBase/` - supplied documents used by the assignment.
- `ingestion/` - PDF, DOCX, and XLSX parsing and structure-aware chunking code.
- `evaluation/` - the permanent ten-case dataset, live runner, raw outputs, and manual judgments.
- `infra/` - reproducible Azure Bicep infrastructure.
- `architecture/` - production diagrams, editable sources, and presentation guidance.
- `tests/` - automated tests.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) - authoritative progress
  tracker and decision journal.

## Git basics

Check what changed and which branch is active:

```powershell
git status
git branch --show-current
git remote -v
```

The expected working branch is `main`. Review `git status` before every commit
to avoid accidentally adding local credentials or generated files.
