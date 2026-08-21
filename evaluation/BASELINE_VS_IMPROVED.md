# Baseline Versus Improved RAG

## Executive summary

The same frozen ten-case `core-v1` dataset was used to evaluate the vector-only baseline and the accepted improved RAG pipeline.

The baseline scored **140/160 (87.5%)**.

The accepted improved pipeline scored **154/160 (96.25%)**, an increase of **14 points**.

## Measured comparison

| Measurement | Baseline RAG | Accepted improved RAG | Change |
|---|---:|---:|---:|
| Manual quality score | 140/160 | 154/160 | +14 points |
| Percentage score | 87.5% | 96.25% | +8.75 percentage points |
| Correctness average | 3.4/4 | 4.0/4 | +0.6 |
| Completeness average | 3.3/4 | 3.9/4 | +0.6 |
| Grounding average | 3.8/4 | 3.9/4 | +0.1 |
| Citation-quality average | 3.5/4 | 3.6/4 | +0.1 |
| Source Hit@5 on eight answerable retrieval cases | 100% | 100% | No change |
| Mean expected-source Recall@5 | 100% | 100% | No change |
| Mean expected-source Precision@5 | 87.5% | 90.0% | +2.5 percentage points |
| Mean live latency | 3,927.51 ms | 3,650.23 ms | 277.28 ms faster |
| Observed p95 latency | 6,596.61 ms | 6,061.73 ms | 534.88 ms faster |

The retrieval measurements are source-level proxies over the eight answerable, non-inventory cases with candidate traces.

They do not replace claim-level semantic relevance review.

The accepted improved run estimated 16,018 total tokens and approximately USD 0.00770582 across ten requests using the dated assumptions in `pricing/azure_openai_assumptions_v1.json`.

The token and cost values are deterministic engineering estimates rather than an Azure billing quote.

## What changed

| Baseline | Improved |
|---|---|
| Fixed 120-word chunks with 20-word overlap | Structure-aware PDF, DOCX, and XLSX chunks |
| Vector-only fixed Top-5 retrieval | Hybrid keyword and vector retrieval with semantic ranking when available |
| Direct Top-5 context | Broad candidate retrieval followed by deterministic fusion and a bounded relevance-first context pack |
| Limited spreadsheet structure | Preserved sheet, table, row, header, grouped-row, and formula context |
| No explicit conversational analysis | Typed ambiguity detection, follow-up rewriting, bounded history, and comparison decomposition |
| Weak handling of document versions | Effective-date, version, current-state, and historical-intent policies |
| Model citation text trusted more directly | Application-owned identifier validation and human-readable citation mapping |
| Generation attempted after ordinary retrieval | Pre-generation evidence sufficiency check and deterministic refusal |

## Representative before-and-after cases

### Document inventory

**Before:** The baseline returned only five of the eleven files and treated two chunks from the same Leave Policy as separate documents.

**After:** The improved application uses indexed source metadata and returns all eleven documents with their department paths.

**Why it improved:** Document inventory became a deterministic Search metadata operation rather than an inferred model answer from arbitrary Top-5 chunks.

### VPN and password requirements

**Before:** The baseline identified the MFA family and password length but omitted the exact VPN portal and did not clearly state the VPN-specific Okta Verify push requirement.

**After:** The improved answer returns `vpn.northwindtraders.example`, Okta Verify push approval, and the twelve-character minimum with both IT sources.

**Why it improved:** Cross-document query analysis, structure-aware chunks, candidate fusion, and relevance-first context selection preserved evidence from both the VPN guide and password policy.

### Spreadsheet discount calculation

**Before:** The baseline found the discount components and calculated price but omitted the Chief Revenue Officer and Finance Business Partner approval requirement.

**After:** The improved answer returns the 20% volume discount, 15% annual discount, 35% combined discount, `$42.25` final monthly price, and both required approvers.

**Why it improved:** XLSX ingestion preserves row headers and grouped sheet context, while multi-facet retrieval reserves volume, term, calculation, and approval evidence.

### Pricing across document versions

**Before:** The baseline estimated the 2026 Starter price from a percentage increase instead of retrieving the exact `$32` value.

**After:** The improved answer returns Starter at `$29` in 2025 and `$32` in 2026, with Advanced Analytics at `$12` and `$14` respectively.

**Why it improved:** Temporal query decomposition retrieves each requested year independently, and version-aware fusion preserves both current and historical evidence.

**Remaining limitation:** The improved answer is factually correct, but one citation uses a general 2026 pricing overview rather than the most precise `$32` chunk.

### Unsupported information

**Before and after:** Both accepted versions refused the unsupported question without fabricated citations.

**Additional protection:** The improved pipeline performs evidence sufficiency checks before generation and rejects unknown, forged, malformed, or ambiguously mapped citation identifiers.

## Evaluation method

Each of the ten cases defines the expected answer, expected sources, expected facts, category, and difficulty.

Every response was manually scored from zero to four for correctness, completeness, grounding, and citation quality.

The maximum score is sixteen points per case and 160 points for the suite.

The dataset is frozen and protected by a SHA-256 check so later versions cannot improve their score by changing the questions.

Run the reproducible evaluation with:

```powershell
.\.venv\Scripts\python.exe -m evaluation.runner --pipeline both
```

## Evidence artifacts

- [Frozen ten-case dataset](datasets/core_v1.json)
- [Evaluation protocol](README.md)
- [Baseline and first-improved raw comparison](results/core_v1_baseline_vs_improved_v0_6.json)
- [Baseline manual judgment](results/core_v1_baseline_vs_improved_v0_6_judgment.json)
- [Accepted improved raw answers and traces](results/core_v1_improved_v0_7_accepted_unscored.json)
- [Accepted improved manual judgment](results/core_v1_improved_v0_7_accepted_judgment.json)

## Honest limitations

- The accepted suite contains ten frozen cases rather than a large production benchmark.
- Retrieval-time department access enforcement remains a production implementation gap.
- Claim-level semantic citation entailment is not yet implemented.
- The current application runs locally while calling live Azure AI services.
- Latency and cost measurements are based on a small sequential assignment workload and should not be treated as production capacity results.
