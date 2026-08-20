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

The local project foundation is **complete**. It currently includes:

- A Python virtual environment and separated runtime/development dependencies.
- Typed environment configuration with safe defaults.
- A minimal FastAPI application with a working `GET /health` endpoint.
- Five configuration/health tests plus Ruff, mypy, and pytest configuration.
- The 11 supplied source documents under `KnowledgeBase/`.
- Placeholder directories for ingestion, evaluation, infrastructure, and
  architecture artifacts.

Document ingestion, Azure infrastructure, search indexes, RAG answering, the
browser UI, and evaluation results are **not implemented yet**.

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the live checklist,
acceptance evidence, and engineering decision journal. That tracker must be
updated whenever an action is completed, including what was done, how it was
verified, and why the approach was chosen.

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

The current health endpoint works without Azure values. Do not commit `.env`,
API keys, access tokens, or connection strings; Git is configured to ignore
them.

## Run the current application

With the virtual environment active, start the API:

```powershell
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/health>. The expected response is:

```json
{
  "status": "ok",
  "service": "enterprise-knowledge-assistant",
  "environment": "development"
}
```

FastAPI's interactive API documentation is available at
<http://127.0.0.1:8000/docs>. Stop the server with `Ctrl+C`.

## Run tests and quality checks

Run these commands from the repository root while the virtual environment is
active:

```powershell
python -m pytest
python -m ruff check .
python -m mypy app ingestion evaluation
python -m pip check
```

At this stage, pytest checks the health endpoint. The quality gates will expand
as ingestion, retrieval, security, and evaluation features are added.

## Planned architecture

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
User question -> retrieve permitted evidence -> rerank results
          |
          v
Azure OpenAI generates a grounded answer
          |
          v
FastAPI returns the answer, validated citations, and diagnostics
```

The baseline will use simpler fixed-size chunks and vector-only retrieval. The
improved version will add structure-aware chunking, hybrid keyword/vector
retrieval, version handling, query rewriting, evidence checks, citations, and
retrieval-time department access control. These are planned capabilities, not
current claims.

## Azure account and cost safety

The local health endpoint and tests do not create Azure resources or consume
Azure credits. Cloud resources will be defined as reproducible Bicep code before
deployment instead of being created ad hoc in the Azure Portal.

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

- `app/` — FastAPI application and runtime configuration.
- `KnowledgeBase/` — supplied documents used by the assignment.
- `ingestion/` — future parsing, chunking, and indexing code.
- `evaluation/` — future evaluation cases, metrics, and reports.
- `infra/` — future Azure Bicep infrastructure.
- `architecture/` — future system diagrams and design artifacts.
- `tests/` — automated tests.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — authoritative progress
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
