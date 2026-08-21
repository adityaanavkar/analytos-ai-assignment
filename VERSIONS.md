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

## Permanent ten-case evaluation protocol

Starting with v0.6, every completed RAG version must run the unchanged `evaluation/datasets/core_v1.json` suite before the version is declared finished.

The suite contains exactly ten stable cases covering corpus inventory, cross-document synthesis, PDF and DOCX facts, XLSX multi-row retrieval, XLSX cross-section retrieval, current pricing, conflicting yearly versions, and missing information.

Every run must preserve the dataset hash, corpus fingerprint, code revision, UTC timestamp, indexes, model deployments, complete answers, citations, retrieved counts, latency, individual judge scores, aggregate score, and candid failure analysis.

The human judge reads every answer against the expected facts and sources, then scores correctness, completeness, grounding, and citation quality from 0 to 4 each for a maximum of 16 per case.

Historical versions v0.0 through v0.5 were not run against these exact frozen bytes and are therefore labeled **Not evaluated on core-v1** rather than given reconstructed scores.

## v0.6 - Frozen baseline and first measured comparison

- **Date and evaluated code:** The live run occurred on 2026-08-21 against commit `34fc956aa5e87d6803fe9556afaaf1c6a510d066` plus the uncommitted v0.6 evaluation implementation that this version records.
- **Objective:** The objective was to create an intentionally simple, reproducible vector-only control and measure the existing improved RAG against the same questions.
- **Achieved:** All 11 documents were flattened into 53 deterministic baseline chunks using fixed 120-word windows with 20-word overlap and uploaded to the separate `enterprise-kb-baseline-v1` Azure Search index.
- **How it works:** The baseline uses `text-embedding-3-small`, vector-only fixed Top-5 retrieval, and `gpt-4.1-mini`, with no keyword search, semantic ranking, query rewrite, decomposition, version preference, or question-specific tuning.
- **How it works:** The current improved pipeline uses the separate 186-chunk structure-aware `enterprise-kb-improved-v1` index and its existing hybrid retrieval path with the same embedding, generation model, and frozen questions.
- **Why:** A weak but fixed control makes retrieval changes measurable and prevents an attractive demonstration from being mistaken for evidence of improvement.
- **Verification and evidence:** The baseline corpus fingerprint is `ba1733838a948e08093db141458d5b7e29302e9b612b9d2108556c1d53b16313`, and the evaluated core-v1 dataset SHA-256 is `9a76a255bd500a6f8a602a633d9c968b7bcaaff89a8b8bf279fa2c6684844f64`.
- **Verification and evidence:** The live baseline upload reconciled 53 chunks with zero stale chunks, and the repository passed 79 tests, Ruff, and strict mypy before evaluation.
- **Raw artifacts:** Complete machine-readable output is in `evaluation/results/core_v1_baseline_vs_improved_v0_6.json`, and the manual score rationale is in `evaluation/results/core_v1_baseline_vs_improved_v0_6_judgment.json`.
- **Measured result:** Baseline scored **140/160 (87.5%)**, while improved scored **141/160 (88.1%)**, an immaterial one-point gain that does not support a claim of meaningful overall improvement.
- **Measured result:** Baseline mean latency was 3,927.51 ms with 6,596.61 ms observed p95, while improved mean latency was 2,921.53 ms with 4,442.92 ms observed p95 across these ten sequential requests, with zero request errors in either pipeline.
- **Known weaknesses or things going badly:** The improved pipeline is much better at complete inventory, but it is worse on the 250-seat spreadsheet calculation and misses the same exact 2026 Starter price as the baseline.
- **Known weaknesses or things going badly:** The improved pipeline also omits the exact VPN portal URL, while the baseline omits that URL and fails to state the VPN-specific push requirement clearly.
- **Next focus:** Fix spreadsheet row coverage, version-aware retrieval, and multi-source evidence completeness, then rerun these exact ten cases without changing them.

### v0.6 scorecard

| Case | Baseline | Improved | Judge finding |
|---|---:|---:|---|
| CORE-001 | 7/16 | 15/16 | Improved lists all 11 files, while baseline returns only five and confuses chunks with documents. |
| CORE-002 | 16/16 | 16/16 | Both answer the finance cross-document question completely. |
| CORE-003 | 12/16 | 11/16 | Both omit the portal URL, and improved has no VPNGuide citation. |
| CORE-004 | 13/16 | 7/16 | Baseline calculates 35% and $42.25 but misses approval, while improved misses nearly the entire deal calculation. |
| CORE-005 | 16/16 | 16/16 | Both answer and cite the HR timing facts correctly. |
| CORE-006 | 16/16 | 16/16 | Both compare the legal survival terms correctly. |
| CORE-007 | 16/16 | 16/16 | Both retrieve the current 2026 Professional values. |
| CORE-008 | 12/16 | 12/16 | Both estimate rather than retrieve the exact 2026 Starter price of $32. |
| CORE-009 | 16/16 | 16/16 | Both refuse the unsupported pet-insurance question correctly. |
| CORE-010 | 16/16 | 16/16 | Both answer the startup-discount spreadsheet question completely. |
| **Total** | **140/160** | **141/160** | **The observed difference is only 0.6 percentage points.** |

### v0.6 complete recorded outputs

The citations below list source paths for readability, while the raw artifact preserves every exact chunk ID, page or section value, retrieved count, and latency.

#### CORE-001 - Baseline - 7/16

> The documents currently in the knowledge base, grouped by department, are: People Operations / HR: LeavePolicy (two documents related to leave and holidays); Finance / Expense Management: ExpensePolicy; Sales Operations: Discounts and Pricing2025.
>
> No other departments or documents are mentioned in the provided evidence.

Citations: `KnowledgeBase/HR/LeavePolicy.pdf`, `KnowledgeBase/Finance/ExpensePolicy.pdf`, `KnowledgeBase/Sales/Discounts.xlsx`, and `KnowledgeBase/Sales/Pricing2025.pdf`.

#### CORE-001 - Improved - 15/16

> 11 documents are indexed: ExpensePolicy, TravelPolicy, Benefits, LeavePolicy, PasswordPolicy, VPNGuide, NDA, VendorContract, Discounts, Pricing2025, and Pricing2026, with each complete KnowledgeBase department path shown.

Citations: None required because this is the deterministic corpus inventory path.

#### CORE-002 - Baseline - 16/16

> For a single $3,000 business-travel expense, it must be submitted through ExpensePath within 30 calendar days of trip completion or purchase date, an itemized receipt is required because it is over the $25 threshold, and approval must come from the Department VP because the amount is between $2,500 and $10,000.

Citations: `KnowledgeBase/Finance/ExpensePolicy.pdf` and `KnowledgeBase/Finance/TravelPolicy.docx`.

#### CORE-002 - Improved - 16/16

> For a single $3,000 business-travel expense, it must be submitted through ExpensePath within 30 calendar days of trip completion or purchase date, an itemized receipt is required because the expense is over $25, and approval must come from the Department VP because the amount is between $2,500 and $10,000.

Citations: `KnowledgeBase/Finance/ExpensePolicy.pdf` and `KnowledgeBase/Finance/TravelPolicy.docx`.

#### CORE-003 - Baseline - 12/16

> The VPN is NorthLink VPN and requires MFA for every connection.
>
> Okta Verify is the primary required MFA method for all Company accounts, with push notification as the preferred factor.
>
> The minimum company password length is 12 characters.

Citations: `KnowledgeBase/IT/VPNGuide.pdf` and `KnowledgeBase/IT/PasswordPolicy.docx`.

#### CORE-003 - Improved - 11/16

> The VPN portal that should be used by a remote employee is the Company VPN portal.
>
> The MFA method required is Okta Verify as the primary method.
>
> The minimum company password length is 12 characters.

Citations: `KnowledgeBase/IT/PasswordPolicy.docx` only.

#### CORE-004 - Baseline - 13/16

> For 250 OrbitSuite seats on an annual prepaid term, the volume discount is 20% and the annual prepaid term discount is 15%, producing a combined 35% discount and a final price of $42.25 from the $65 list price.
>
> No CFO exception is needed, but the exact approver is not specified in the retrieved evidence.

Citations: `KnowledgeBase/Sales/Discounts.xlsx`.

#### CORE-004 - Improved - 7/16

> The evidence does not provide the exact combined discount and final monthly per-seat price specifically for 250 OrbitSuite seats on an annual prepaid term.
>
> Annual prepaid contracts receive a 15% discount, but the final monthly per-seat price and approver are not specified in the retrieved evidence.

Citations: `KnowledgeBase/Sales/Pricing2026.pdf`, `KnowledgeBase/Sales/Discounts.xlsx`, and `KnowledgeBase/Sales/Pricing2025.pdf`.

#### CORE-005 - Baseline - 16/16

> A new full-time employee begins accruing PTO on a bi-weekly basis starting on the first day of employment.
>
> Benefits coverage begins on the first day of the month following 30 days of employment.

Citations: `KnowledgeBase/HR/LeavePolicy.pdf` and `KnowledgeBase/HR/Benefits.pdf`.

#### CORE-005 - Improved - 16/16

> A new full-time employee begins accruing PTO on a bi-weekly basis starting on the first day of employment.
>
> Benefits coverage begins on the first day of the month following 30 days of employment.

Citations: `KnowledgeBase/HR/LeavePolicy.pdf` and `KnowledgeBase/HR/Benefits.pdf`.

#### CORE-006 - Baseline - 16/16

> Mutual NDA confidentiality survives three years after disclosure and indefinitely for trade secrets.
>
> Vendor Agreement confidentiality survives five years after termination and indefinitely for trade secrets.

Citations: `KnowledgeBase/Legal/NDA.docx` and `KnowledgeBase/Legal/VendorContract.pdf`.

#### CORE-006 - Improved - 16/16

> Mutual NDA confidentiality survives three years after disclosure and indefinitely for trade secrets.
>
> Vendor Agreement confidentiality survives five years after termination and indefinitely for trade secrets.

Citations: `KnowledgeBase/Legal/NDA.docx` and `KnowledgeBase/Legal/VendorContract.pdf`.

#### CORE-007 - Baseline - 16/16

> The current 2026 Professional tier monthly list price is $65 per seat per month, and its API limit is 100,000 calls per month.

Citations: `KnowledgeBase/Sales/Pricing2026.pdf`.

#### CORE-007 - Improved - 16/16

> The current 2026 Professional tier monthly list price is $65 per seat per month, and its API limit is 100,000 calls per month.

Citations: `KnowledgeBase/Sales/Pricing2026.pdf`.

#### CORE-008 - Baseline - 12/16

> The 2025 Starter price is $29 and the 2025 Advanced Analytics add-on is $12.
>
> The 2026 Advanced Analytics add-on is $14, but the exact Starter price was not retrieved and was estimated at $31.32 to $31.90 from an 8 to 10 percent increase.

Citations: `KnowledgeBase/Sales/Pricing2025.pdf` and `KnowledgeBase/Sales/Pricing2026.pdf`.

#### CORE-008 - Improved - 12/16

> The 2025 Starter price is $29 and the 2025 Advanced Analytics add-on is $12.
>
> The 2026 Advanced Analytics add-on is $14, but the exact Starter price was not retrieved and was estimated at $31.32 to $31.90 from an 8 to 10 percent increase.

Citations: `KnowledgeBase/Sales/Pricing2025.pdf` and `KnowledgeBase/Sales/Pricing2026.pdf`.

#### CORE-009 - Baseline - 16/16

> I could not find enough supporting information in the knowledge base to answer that.

Citations: None.

#### CORE-009 - Improved - 16/16

> I could not find enough supporting information in the knowledge base to answer that.

Citations: None.

#### CORE-010 - Baseline - 16/16

> The Year 1 startup discount is 30%.
>
> It cannot stack with volume or term discounts, and only the highest applicable single discount applies.
>
> Eligibility is checked annually.

Citations: `KnowledgeBase/Sales/Discounts.xlsx`.

#### CORE-010 - Improved - 16/16

> The Year 1 startup discount is 30%.
>
> It cannot stack with volume or term discounts, and only the highest applicable single discount applies.
>
> Eligibility is checked annually.

Citations: `KnowledgeBase/Sales/Discounts.xlsx`.
