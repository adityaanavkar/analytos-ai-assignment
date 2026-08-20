# Project Version History

This file explains how the assignment evolved from source files into a live Azure RAG demonstration.

The entries are reconstructed from Git history and `IMPLEMENTATION_PLAN.md`.

They describe only evidence that exists in the repository or was recorded in the implementation tracker.

The version numbers are documentation labels because the repository does not yet contain Git release tags.

## Version update rule

Every meaningful working checkpoint must update this file in the same delivery change.

Each entry must record the objective, achieved behavior, implementation approach, verification evidence, known weaknesses, and next focus.

Known failures and disappointing behavior must be recorded candidly instead of being omitted from the version narrative.

## v0.0 - Assignment bootstrap

- **Date and commit:** This version was committed on 2026-08-20 as `c61a077` (`chore: initialize Azure RAG assignment`).
- **Objective:** The objective was to preserve the assignment, its source documents, and the initial Python dependency choices in Git.
- **Achieved:** The repository gained the assignment brief, discussion notes, seven PDF files, three DOCX files, one XLSX workbook, dependency files, and basic ignore rules.
- **How it works:** At this stage the repository was a source corpus and dependency manifest rather than a runnable application.
- **Verification and evidence:** Git records 11 knowledge-base documents and the tracker records that all seven PDFs, three DOCX files, and one XLSX workbook could be opened by their parsers.
- **Known weaknesses or things going badly:** There was no API, ingestion pipeline, Azure infrastructure, retrieval path, user interface, or automated application test.
- **Next focus:** The next priority was a cloud-independent application foundation with typed settings, tests, and an auditable execution tracker.

## v0.1 - Local application foundation

- **Date and commit:** This version was committed on 2026-08-21 as `4445afd` (`chore: establish assignment foundation`).
- **Objective:** The objective was to make the repository runnable, testable, safe for local development, and understandable to a beginner or reviewer.
- **Achieved:** The project gained FastAPI configuration, a health endpoint, typed environment settings, an example environment file, quality-tool configuration, tests, a README, and the implementation tracker.
- **How it works:** `GET /health` starts without contacting Azure, while Pydantic validates the complete set of required configuration when live Azure mode is enabled.
- **Verification and evidence:** The tracker records a clean repository foundation, five passing tests, Ruff and formatting success, strict mypy success, 100 percent application coverage at that checkpoint, and a clean `pip check`.
- **Known weaknesses or things going badly:** The application could report health but could not yet ingest a document, search Azure, generate an answer, or display a functional RAG result.
- **Next focus:** The next priority was a thin live vertical slice that exercised document parsing, embeddings, search, generation, citations, API delivery, and browser delivery together.

## v0.2 - First live Azure RAG MVP

- **Date and commit:** This version was committed on 2026-08-21 as `c3f573b` (`feat: deliver end-to-end Azure RAG MVP`).
- **Objective:** The objective was to prove the riskiest Azure and application boundaries with one real document before building broader ingestion or retrieval features.
- **Achieved:** Bicep infrastructure, direct Azure SDK adapters, PDF extraction and chunking, Azure Search indexing, Azure OpenAI embeddings and generation, citation validation, a chat API, and a minimal browser page were connected end to end.
- **How it works:** The system extracts `ExpensePolicy.pdf`, creates stable chunks, generates 1,536-dimensional embeddings with `text-embedding-3-small`, performs hybrid Azure AI Search retrieval, and asks `gpt-4.1-mini` to answer only from retrieved evidence with chunk citations.
- **Verification and evidence:** The tracker records a successful live HTTP 200 answer that correctly described the 30-day and 60-day expense-submission rules, retrieved four chunks, and cited page 1 of the source PDF.
- **Verification and evidence:** The Azure deployment was created through reviewed Bicep in `rg-analytos-ai-demo`, and a live embedding smoke check returned the required 1,536 dimensions.
- **Known weaknesses or things going badly:** The MVP covered only one PDF, one improved index, fixed-size chunks, and a minimal single-question interface.
- **Known weaknesses or things going badly:** The first version failed badly on greetings and unsupported text because an uncited model response triggered citation validation and escaped as a plain-text HTTP 500.
- **Next focus:** The immediate priority was predictable behavior for greetings, missing evidence, and provider failures without weakening citation validation for supported answers.

## v0.2.1 - Chat failure and greeting hardening

- **Date and commit:** This version was committed on 2026-08-21 as `35ac636` (`fix: handle greetings and chat failures safely`).
- **Objective:** The objective was to prevent harmless inputs and backend failures from producing opaque or unsafe HTTP 500 responses.
- **Achieved:** Exact greetings gained a deterministic response, unsupported or uncited answers gained a deterministic insufficient-evidence response, and unexpected provider errors gained sanitized JSON handling.
- **How it works:** Greeting detection bypasses retrieval, no-evidence paths return no fabricated citations, citation IDs are still validated for grounded answers, and the API converts unexpected answer failures to a stable JSON error.
- **Verification and evidence:** The tracker records live JSON HTTP 200 responses for `Hi`, `whjat`, and a supported Expense Policy question.
- **Verification and evidence:** The supported question retained its verified page citation, while the regression suite passed 40 tests at this checkpoint.
- **Known weaknesses or things going badly:** Greeting handling was intentionally narrow, and the system still had no query rewriting, ambiguity analysis, conversation memory, or calibrated evidence threshold.
- **Next focus:** The next priority was to ingest every supplied file format and make corpus inventory questions deterministic.

## v0.3 - Complete 11-document corpus and inventory

- **Date and commit:** This version was committed on 2026-08-21 as `5de0f38` (`feat: index complete enterprise knowledge base`).
- **Objective:** The objective was to replace the one-document demonstration with one repeatable ingestion path for the entire supplied corpus.
- **Achieved:** PDF, DOCX, and XLSX inputs were unified into a live upload command, all 11 documents were reconciled into the assignment index as 186 chunks, and deterministic corpus inventory queries were added.
- **How it works:** Format-specific parsers preserve PDF pages, Word headings and tables, and Excel sheets, rows, and table headers before 1,536-dimensional embeddings are created in batches and stable chunk IDs are upserted.
- **How it works:** The reconciliation step removes stale IDs only from the dedicated assignment index, which makes repeated runs predictable without deleting unrelated Azure data.
- **Verification and evidence:** The tracker records two consecutive live uploads with 11 documents, 186 chunks, zero failed uploads, and zero stale chunks.
- **Verification and evidence:** Live chat listed all 11 documents, returned exactly two Finance documents for a department inventory question, and answered cited questions from both DOCX and XLSX sources.
- **Verification and evidence:** The automated suite passed 63 tests at this checkpoint.
- **Known weaknesses or things going badly:** This milestone completed corpus availability but did not complete the formal ingestion action because Blob input unification, bounded concurrency, retry and backoff, partial-failure handling, and richer canonical metadata were still missing.
- **Known weaknesses or things going badly:** Broad table and multi-row retrieval remained vulnerable to incomplete evidence, and no frozen baseline comparison had been run.
- **Next focus:** The next priority was improving the user experience while preserving the working API and then returning to measurable retrieval quality, security, and evaluation work.

## v0.4 - Experimental dashboard interface

- **Date and commit:** This version was committed on 2026-08-21 as `34d18f5` (`feat: refresh knowledge assistant interface`).
- **Objective:** The objective was to explore a more polished reviewer-facing presentation for the working knowledge assistant.
- **Achieved:** The minimal page became a responsive two-panel dashboard with a large introduction, query suggestions, loading and error states, an answer panel, citation rendering, and corpus summary cards.
- **How it works:** A single static HTML file calls the existing `POST /chat` endpoint and updates the page with the answer, retrieved-chunk count, and citation locations.
- **Verification and evidence:** The commit changes only `app/static/index.html`, and the existing UI smoke coverage verifies that the page loads and retains its chat form and API call.
- **Known weaknesses or things going badly:** The interface is experimental rather than a completed product decision.
- **Known weaknesses or things going badly:** The `Azure live` badge and the values for 11 documents, 186 fragments, and five departments are hard-coded, so they are not trustworthy runtime telemetry.
- **Known weaknesses or things going badly:** The large dashboard framing gives more space to presentation than conversation and still supports only a single visible answer rather than an ongoing chat.
- **Next focus:** The next priority is a chat-first interface that makes asking follow-up questions and reading citations the central experience.

## v0.5 - Chat-first interface

- **Date and commit:** This version was completed on 2026-08-21 from `34d18f5`, and its delivery commit is recorded by the Git history containing this file.
- **Objective:** The objective was to replace the experimental dashboard emphasis with a focused conversational layout suitable for repeated questions and clear source review.
- **Achieved:** The page now has a compact sidebar, a central scrolling conversation, a sticky composer, multiple visible client-side turns, suggestion prompts, new-chat reset, loading and error states, retrieved counts, and collapsible citations per answer.
- **How it works:** The static client preserves the existing `POST /chat` contract, appends user and assistant turns safely with DOM text nodes, supports Enter to send and Shift+Enter for a newline, and adapts the sidebar into a compact mobile header.
- **Verification and evidence:** Four focused UI tests and 11 combined UI/API tests passed, followed by a repository-wide run of 65 passing tests, Ruff, formatting, strict mypy, a clean whitespace check, and a browser-level visual review.
- **Known weaknesses or things going badly:** Conversation history exists only in the browser and is not sent to the backend, so follow-up questions do not yet gain conversational understanding.
- **Known weaknesses or things going badly:** Responses are not streamed, corpus counts remain static presentation data, and the UI does not yet expose department identity, baseline-versus-improved mode, confidence, latency, or diagnostics.
- **Known weaknesses or things going badly:** The broader tracker still shows that canonical metadata, baseline measurement, query analysis, retrieval-time ACLs, formal evaluation, observability, and final architecture deliverables remain incomplete.
- **Next focus:** The next engineering milestone is A5, which freezes a vector-only baseline and preserves measurable results before further retrieval improvements are introduced.

## Current engineering status

The working system is a real Azure-backed, multi-format RAG demonstration, but it is not yet the completed assignment.

The master checklist currently contains three complete actions, five in-progress actions, and seven pending actions across P0 and A1 through A14.

The tracker currently marks A6, A8, and A10 as in progress in the master checklist while their detailed journal lines still say pending.

That mismatch is a documentation weakness and should be reconciled in the next tracker update rather than treated as implementation evidence.

The strongest verified result is complete local-corpus availability with live grounded answers and validated citations across PDF, DOCX, and XLSX sources.

The largest remaining proof gap is the frozen baseline-versus-improved evaluation, because retrieval improvement must be demonstrated with measured results rather than asserted.

The largest remaining production gap is retrieval-time departmental access control backed by validated identity claims.

After the active chat-first UI work, the recommended engineering milestone is A5, which must freeze a vector-only baseline and preserve immutable measured results before improved retrieval is evaluated.

`IMPLEMENTATION_PLAN.md` remains the source of truth for action status, acceptance criteria, and detailed completion evidence.
