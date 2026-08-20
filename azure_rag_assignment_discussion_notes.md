# Senior AI Engineer Azure RAG Assignment — Working Notes & Execution Plan

## 1. Context

You received a **Senior AI Engineer – Technical Assignment** focused on:

- Microsoft Azure AI
- Retrieval-Augmented Generation (RAG)
- Enterprise architecture
- Retrieval/debugging methodology
- RAG evaluation
- Production considerations such as security, scaling, cost, and monitoring

The recruiter/company also mentioned a screening condition along the lines of:

> “2 years of Azure AI Services experience, then only submit the next-round technical task.”

You do **not** currently have two full years specifically working with Azure AI Services.

---

# 2. What “2 Years of Azure AI Services Experience” Means

This normally means hands-on experience using Microsoft's Azure AI/ML ecosystem, such as:

- Azure OpenAI / Microsoft Foundry model deployments
- Azure AI Search
- Azure Machine Learning
- Azure AI Foundry / Microsoft Foundry
- Azure AI Document Intelligence
- Azure Vision / Speech
- Azure-hosted model endpoints
- Azure Storage
- Azure Functions / App Service
- Azure Monitor / Application Insights
- Entra ID / Azure RBAC
- Key Vault / managed identities
- Private networking / private endpoints

It does **not** simply mean “2 years of general AI/ML experience.”

Someone with strong ML, RAG, GCP, AWS, Kubernetes, FastAPI, or production AI experience can usually learn the Azure equivalents relatively quickly, but that is still different from having two years of direct Azure AI production experience.

## Should You Still Apply?

Yes, applying is reasonable if the application itself is low effort.

However:

- Do **not** claim two years of Azure AI experience if you do not have it.
- Do not spend a large amount of time on a take-home assignment if they will automatically reject candidates without that experience.
- Ideally, get confirmation that they are still happy for you to proceed.

A reasonable positioning is:

> Strong production AI/ML and cloud experience, primarily outside Azure, with the ability to ramp quickly on Azure AI Services.

---

# 3. Extension Request

Because the assignment is substantial and you received it during the work week, you requested additional time.

The polished message was:

> Hi Santosh,
>
> Glad to hear that I’ve been selected for the technical screening round at Analytos.ai.
>
> I went through the assignment and would like to give it a fair and thorough attempt. I received the assignment this afternoon and have started working on it, but I also have ongoing office commitments. To ensure I can dedicate sufficient time and submit a quality solution, I’d like to request an extension until **Sunday, 23rd August**.
>
> Please let me know if that works for you.
>
> Thank you for your consideration.
>
> Best regards,  
> Aditya

---

# 4. Assignment Requirements

The assignment is effectively a small production-style RAG project.

## Step 1 — Build a RAG Knowledge Assistant

Expected flow:

```text
Documents
   ↓
Parsing
   ↓
Chunking
   ↓
Embeddings
   ↓
Azure AI Search
   ↓
Retrieval / Reranking
   ↓
Context
   ↓
LLM
   ↓
Grounded Answer + Citations
```

Recommended stack from the assignment:

- Azure OpenAI
- Azure AI Search
- Azure AI Foundry / Microsoft Foundry
- Azure Storage
- Azure Functions / App Service
- Application Insights
- Python for core application

The UI can be very simple.

---

## Step 2 — Production Architecture

Need an architecture diagram covering:

- document ingestion
- Azure AI Search
- Azure OpenAI
- application/API layer
- authentication
- secrets management
- monitoring
- scaling
- security
- data isolation
- cost

Need to explain:

- Why this architecture?
- Why Azure AI Search?
- Semantic vs vector vs hybrid search?
- What changes from 10,000 documents to 10 million documents?

---

## Step 3 — RAG Failure Scenarios

You need to demonstrate/debug several common RAG problems.

### Scenario 1 — Correct Document, Wrong Chunk

Potential issues:

- poor chunk size
- poor chunk overlap
- embedding quality
- Top-K too low/high
- metadata filtering
- vector-only retrieval weakness
- lack of reranking

Possible improvements:

- better chunk boundaries
- hybrid BM25 + vector retrieval
- metadata filters
- reranking
- tuning Top-K

---

### Scenario 2 — Information Across Multiple Sections

Example:

> Compare the refund policy for Enterprise and Standard customers.

Need retrieval that can gather multiple relevant chunks and synthesize them.

Possible approach:

1. Rewrite/decompose query.
2. Retrieve for each subtopic.
3. Merge results.
4. Deduplicate.
5. Rerank.
6. Give the LLM both relevant sections.

---

### Scenario 3 — Similar Documents / Conflicting Information

Example:

```text
Leave_Policy_2024.pdf
Leave_Policy_2026.pdf
```

Need to prefer current policy.

Use metadata such as:

- document version
- effective date
- publication date
- active/inactive status
- department
- policy type

Then:

- filter obsolete documents, or
- boost newer versions during ranking.

---

### Scenario 4 — Hallucination / Missing Information

If the answer is not in the knowledge base, the system should not fabricate.

Possible approach:

- retrieval score threshold
- reranker score threshold
- evidence sufficiency check
- require citations
- prompt explicitly instructs model not to answer without evidence
- optional LLM-based groundedness/evidence classifier

Expected response style:

> I could not find enough information in the provided documents to answer this reliably.

---

### Scenario 5 — Ambiguous Query

Example:

> What is the limit?

Possible policy:

1. Check conversation context.
2. If context resolves ambiguity, rewrite the query using that context.
3. Otherwise ask a clarification question instead of guessing.

---

### Scenario 6 — Conversational Context

Example:

```text
User: What is the Enterprise plan cancellation policy?
User: What about Standard?
User: Is there any exception?
```

Do **not** simply append the entire chat history to retrieval.

Better approach:

```text
Conversation context
      ↓
Standalone query rewrite
      ↓
Retriever
```

For example:

```text
"What about Standard?"
```

becomes:

```text
"What is the Standard plan cancellation policy?"
```

The retriever then searches using the rewritten standalone query.

---

# 5. Evaluation Requirements

Need a small evaluation dataset containing:

- straightforward questions
- multi-document questions
- ambiguous questions
- unanswered questions
- follow-up questions

Suggested evaluation fields:

```text
question
expected_answer
expected_document
expected_section
difficulty
question_type
```

Recommended dataset size for this assignment:

**~15–25 questions**

Enough to demonstrate methodology without turning it into a research project.

---

## Retrieval Metrics

Possible metrics:

- Hit Rate / Hit@K
- Recall@K
- MRR if useful
- relevance of retrieved chunks
- expected-document retrieval
- expected-section retrieval

Example:

```text
Hit@5 = number of questions where the expected source appeared
        in the top 5 retrieved chunks
        /
        total answerable questions
```

---

## Generation Metrics

Measure:

- answer correctness
- groundedness
- citation correctness
- hallucination rate
- refusal quality for missing-information questions

---

## System Metrics

Track:

- end-to-end latency
- retrieval latency
- LLM latency
- token usage
- approximate cost

---

## Key Evaluation Story

The presentation should clearly show:

```text
Baseline RAG
     ↓
Identify failures
     ↓
Apply improvements
     ↓
Re-run evaluation
     ↓
Compare metrics
```

This is one of the most important parts of the assignment.

---

# 6. Time Estimate Without Heavy AI Assistance

For a proper submission built mostly manually:

| Work | Estimated Time |
|---|---:|
| Azure setup | 1–2 h |
| Parsing/chunking/embeddings | 1.5–2 h |
| Basic RAG API/chat | 1–1.5 h |
| Hybrid search / metadata / reranking | 2–3 h |
| Failure scenarios | 2–3 h |
| Evaluation | 1.5–2.5 h |
| Architecture + technical answers | 1–1.5 h |
| README | ~1 h |
| Video | 0.5–1 h |
| **Total** | **~12–18 h** |

A minimal but defensible submission could potentially be done in:

**~8–10 hours**

---

# 7. Time Estimate With GPT-5.6 Sol / AI Coding Tools

If all documents, requirements, test questions, resource details, and assignment instructions are provided to GPT-5.6 Sol and AI coding tools are used aggressively, the manual effort can drop significantly.

Estimated personal effort:

| Work | Estimated Time |
|---|---:|
| Analyze requirements/docs | 15–30 min |
| Generate repo + initial implementation | 30–60 min |
| Azure setup/config | 30–60 min |
| Live integration debugging | 1–2 h |
| Failure scenarios/improvements | 30–60 min |
| Evaluation | 30–60 min |
| Architecture/README/answers | 20–40 min |
| Video | 20–30 min |
| **Total** | **~4–7 focused hours** |

The largest unpredictable component is Azure configuration/debugging, not writing Python.

Examples of issues that can consume time:

- authentication/RBAC
- wrong endpoint
- wrong deployment name
- unsupported API version
- index schema mismatch
- semantic ranker availability
- region/model availability
- quota restrictions
- vector dimensions mismatch
- permissions

---

# 8. What Azure OpenAI Is

Azure OpenAI is essentially access to OpenAI-family models through the Microsoft Azure ecosystem.

Conceptually:

```text
Your Application
       ↓
Azure / Microsoft Foundry endpoint
       ↓
GPT / embedding model
```

Instead of using a standard OpenAI endpoint directly, the application uses an Azure-managed model deployment.

Enterprise advantages include:

- Azure RBAC
- Entra ID authentication
- Azure networking
- centralized Azure billing
- Key Vault integration
- monitoring
- governance
- private endpoints
- enterprise compliance controls

---

# 9. Can Azure OpenAI Be Replaced With a Free Alternative?

Technically: **yes**.

For example:

```text
Azure OpenAI GPT
       ↓
replace with
       ↓
Ollama + Qwen / Llama / Gemma
```

Similarly, embeddings could be generated locally with:

- sentence-transformers
- BGE
- E5
- Nomic embeddings
- Ollama embedding models

Example architecture:

```text
Documents
   ↓
Local embedding model
   ↓
Azure AI Search
   ↓
Ollama + Qwen
   ↓
Answer
```

This could make inference effectively free.

## Should You Do This for the Assignment?

Probably **not as the primary submission**.

The assignment explicitly asks for:

- Azure OpenAI integration
- Azure AI services
- Azure architecture knowledge

Replacing Azure OpenAI entirely would remove one of the main things they are evaluating.

A better engineering approach is to support multiple providers:

```text
LLM_PROVIDER=local
     ↓
Ollama

LLM_PROVIDER=azure
     ↓
Azure OpenAI
```

This lets most development happen locally while still demonstrating the actual Azure integration in the final submission.

---

# 10. Expected Azure Cost

For a small technical assignment, Azure cost should be very low.

The expensive enterprise architecture does **not** need to be fully deployed.

## Actual Demo

Deploy/use only what is necessary:

```text
Documents
    ↓
Python ingestion
    ↓
Azure OpenAI embeddings
    ↓
Azure AI Search
    ↓
Hybrid retrieval
    ↓
Azure OpenAI
    ↓
Local FastAPI
    ↓
Local UI
```

Potential cost:

- Azure AI Search Free tier: potentially ₹0
- Local FastAPI: ₹0
- Local Streamlit/UI: ₹0
- Storage: negligible
- Azure OpenAI embeddings: small token usage
- Azure OpenAI generation: small token usage

For this assignment-sized workload, a sensible budget target is approximately:

**₹0 with applicable Azure credit**

or approximately:

**well below ₹500–₹1,000 without credit**, assuming careful use.

The exact charge depends on model, region, token counts, and current Azure pricing.

---

# 11. Do Not Deploy the Entire Production Architecture

The assignment asks for an architecture showing how the solution **would** be deployed in production.

That does not mean every component must actually be provisioned.

## Practical Demo Architecture

```text
Documents
     ↓
Python parser
     ↓
Chunker
     ↓
Azure OpenAI embeddings
     ↓
Azure AI Search
     ↓
Hybrid Retrieval
     ↓
Reranker / metadata logic
     ↓
Azure OpenAI
     ↓
FastAPI
     ↓
Simple local UI
```

## Production Architecture Diagram

Show something closer to:

```text
                Enterprise Users
                       ↓
                    Entra ID
                       ↓
                 API Management
                       ↓
                  App Service
                       ↓
                RAG Application
                  ↙          ↘
       Azure AI Search     Azure OpenAI
              ↑
       Ingestion Pipeline
              ↑
         Blob Storage

Cross-cutting services:
- Key Vault
- Managed Identities
- Application Insights
- Azure Monitor
- Private Endpoints
- RBAC / ACL metadata
- Network isolation
- autoscaling
```

You can discuss these production capabilities without provisioning all of them.

---

# 12. Recommended Submission Scope

Do not try to implement every possible Azure feature.

A high-value submission would focus on:

## Core

- Python
- FastAPI
- Azure OpenAI
- Azure AI Search
- document ingestion
- chunking
- embeddings
- vector retrieval
- keyword/BM25 retrieval
- hybrid retrieval
- citations

## Strong Improvements

- metadata filtering
- document version handling
- query rewriting
- conversational standalone-query generation
- reranking
- hallucination/no-answer behavior
- evaluation pipeline
- baseline vs improved metrics

## Optional / Bonus

Only if time permits:

- caching
- App Insights instrumentation
- automated evaluators
- ACL/document access filtering
- confidence scoring
- Docker
- CI
- Bicep/Terraform

---

# 13. Recommended Retrieval Strategy

For this assignment, **hybrid retrieval** is likely the best default.

## Vector Search

Good for:

- semantic similarity
- paraphrased questions
- conceptual matches

Weakness:

- can miss exact names, codes, policy terms, dates, IDs.

---

## Keyword / BM25 Search

Good for:

- exact terminology
- names
- codes
- numbers
- policy titles
- specialized enterprise terms

Weakness:

- poor when user wording differs significantly from document wording.

---

## Hybrid Search

Combine:

```text
BM25 results
     +
Vector results
     ↓
Fusion / RRF
     ↓
Reranking
```

This gives a much stronger story than pure vector retrieval.

A reasonable improved pipeline:

```text
User Query
    ↓
Conversation-aware query rewrite
    ↓
Metadata filters
    ↓
Hybrid BM25 + Vector Search
    ↓
Top 10–20 candidates
    ↓
Semantic / LLM / cross-encoder reranker
    ↓
Top 4–6 chunks
    ↓
Evidence sufficiency check
    ↓
LLM
    ↓
Grounded Answer + Citations
```

---

# 14. Version-Aware Retrieval

For documents such as:

```text
Leave_Policy_2024.pdf
Leave_Policy_2026.pdf
```

Store metadata such as:

```json
{
  "document_type": "leave_policy",
  "version": "2026",
  "effective_date": "2026-01-01",
  "is_current": true,
  "department": "HR"
}
```

Then either:

1. Filter to `is_current = true`, or
2. Apply a freshness/ranking boost to the latest effective date.

This is much stronger than relying on embedding similarity alone.

---

# 15. Access-Controlled RAG

Requirement:

HR documents must never be retrieved for Engineering users.

Do not retrieve everything and then hide unauthorized results after retrieval.

Instead:

```text
Authenticated user
      ↓
Entra ID claims / group memberships
      ↓
Build ACL filter
      ↓
Azure AI Search query
      ↓
Only authorized chunks are eligible for retrieval
```

Possible indexed metadata:

```text
allowed_groups = ["HR", "Legal"]
department = "HR"
tenant_id = "..."
```

Security filtering must happen during retrieval.

---

# 16. Hallucination Prevention

A reasonable strategy:

```text
Query
  ↓
Retrieve candidates
  ↓
Rerank
  ↓
Check retrieval confidence / evidence quality
  ↓
If weak:
    refuse / state insufficient evidence
Else:
    generate answer
  ↓
Validate citations
```

Prompt instruction alone is not sufficient.

Use a combination of:

- retrieval thresholds
- relevance scores
- reranker score
- citation requirement
- groundedness checks
- explicit no-answer evaluation cases

---

# 17. Debugging a Wrong Answer With a Valid-Looking Citation

The debugging sequence should be systematic:

```text
User Query
   ↓
Query Rewrite
   ↓
Search / Retrieval
   ↓
Ranking / Reranking
   ↓
Selected Context
   ↓
Prompt Construction
   ↓
LLM Generation
   ↓
Citation Mapping
```

Check each stage independently.

Questions to ask:

1. Was the original query understood correctly?
2. Was query rewriting correct?
3. Did the correct document enter Top-K?
4. Did the correct chunk enter Top-K?
5. Did reranking accidentally demote the correct chunk?
6. Was the correct chunk passed to the LLM?
7. Did prompt instructions bias the answer incorrectly?
8. Did the LLM misunderstand the context?
9. Did the citation mapper attach the wrong source to the generated sentence?
10. Is stale or conflicting document metadata involved?

This methodology matters more than giving one isolated fix.

---

# 18. GPT-5.6 Sol Can Offload Most of the Assignment

The assignment explicitly permits AI coding tools.

Given:

- the complete assignment
- supplied documents
- training questions
- test questions
- Azure resource information
- desired implementation style

GPT-5.6 Sol can generate a large portion of the repository.

Possible repo:

```text
azure-rag-assignment/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── rag.py
│   ├── retrieval.py
│   ├── query_rewrite.py
│   ├── reranker.py
│   └── citations.py
│
├── ingestion/
│   ├── parser.py
│   ├── chunker.py
│   ├── embeddings.py
│   └── index_documents.py
│
├── evaluation/
│   ├── dataset.json
│   ├── evaluate_retrieval.py
│   ├── evaluate_generation.py
│   └── compare_results.py
│
├── tests/
│
├── architecture/
│   └── architecture.md
│
├── .env.example
├── requirements.txt
├── README.md
└── Dockerfile
```

GPT can assist with:

- project scaffolding
- ingestion code
- chunking logic
- Azure AI Search schema
- embeddings
- vector retrieval
- BM25/hybrid retrieval
- RRF
- metadata filters
- version handling
- query rewriting
- conversational context
- reranking
- citations
- missing-information handling
- evaluation dataset
- retrieval metrics
- groundedness checks
- latency measurement
- token/cost tracking
- FastAPI
- Streamlit/simple frontend
- Dockerfile
- architecture diagram source
- README
- technical-question answers
- presentation structure
- 5-minute video script
- Azure CLI commands
- Bicep/Terraform if wanted

---

# 19. What You Still Need to Do Personally

Even with heavy AI assistance, you need to own four areas.

## 1. Azure Authentication

You need to:

- sign into Azure
- select subscription/resource group
- provision or access resources
- obtain the necessary endpoint/deployment information

---

## 2. Execute Resource Creation

GPT can generate:

```bash
az ...
```

or Bicep/Terraform, but you execute it against your Azure subscription.

---

## 3. Run and Debug the Real System

Typical workflow:

```text
Generate implementation
      ↓
Run locally
      ↓
Azure error
      ↓
Inspect error
      ↓
Fix config/code
      ↓
Run again
```

This is where much of your actual time will go.

---

## 4. Understand and Defend the Architecture

The assignment explicitly says the candidate must personally explain the design.

You should be comfortable answering:

- Why hybrid search?
- Why not vector-only?
- Why this chunk size?
- Why this chunk overlap?
- Why Top-K = N?
- Why rerank?
- Why query rewriting?
- How are obsolete documents handled?
- What happens when the answer does not exist?
- How do ACLs work?
- Why can a citation still be wrong?
- How did Hit@K improve?
- What increased latency?
- How would you scale to millions of documents?
- Where would caching help?
- How would you reduce token cost?

You do not need to manually type every line of code.

You **do** need to understand every major design decision.

---

# 20. Suggested Division of Work

Approximate target:

## AI tools / GPT — ~80–90%

- code generation
- scaffolding
- repetitive implementation
- test generation
- evaluation framework
- architecture drafting
- documentation
- diagrams
- technical explanations

## You — ~10–20%

- Azure account/configuration
- execution
- troubleshooting
- validating results
- choosing final design
- understanding trade-offs
- recording demo
- defending decisions

This is consistent with the assignment because the instructions explicitly allow AI coding tools.

---

# 21. Highest ROI Implementation

A strong, time-efficient submission would be:

```text
Documents
    ↓
Parser
    ↓
Metadata-aware chunking
    ↓
Azure OpenAI embeddings
    ↓
Azure AI Search
    ↓
Hybrid BM25 + vector retrieval
    ↓
Metadata filtering
    ↓
Reranking
    ↓
Evidence sufficiency / no-answer check
    ↓
Azure OpenAI generation
    ↓
Grounded answer + citations
    ↓
FastAPI
```

Add:

- conversation-aware standalone query rewriting
- version-aware filtering
- ~20 evaluation questions
- baseline vs improved metrics
- production architecture diagram

That gives strong coverage of the scoring areas without unnecessary frontend/infrastructure work.

---

# 22. Baseline vs Improved RAG Plan

## Baseline

Keep the baseline intentionally simple:

```text
Fixed-size chunks
      ↓
Vector search
      ↓
Top 5
      ↓
LLM
```

Measure:

- Hit@5
- answer correctness
- groundedness
- hallucination rate
- latency

---

## Improved

Then add:

```text
Structure-aware chunking
        +
Hybrid retrieval
        +
Metadata filters
        +
Document version logic
        +
Query rewriting
        +
Reranking
        +
Evidence sufficiency
```

Re-run the exact same dataset.

Example results table:

| Metric | Baseline | Improved |
|---|---:|---:|
| Hit@5 | 70% | 95% |
| Answer correctness | 65% | 90% |
| Groundedness | 78% | 96% |
| Citation accuracy | 72% | 95% |
| Hallucination rate | 18% | 3% |
| Avg latency | 2.8 s | 3.5 s |

These numbers are examples only. The final submission must use measured results from the actual implementation.

---

# 23. Five-Minute Demo Structure

A concise video could be:

## 0:00–0:40 — Architecture

Explain:

- ingestion
- Azure AI Search
- Azure OpenAI
- FastAPI
- production security/monitoring

## 0:40–1:30 — Working Chatbot

Show:

- one normal question
- answer
- citations

## 1:30–2:30 — Failure Example

Show baseline failure:

- wrong chunk
- stale document
- ambiguous question
- hallucination

## 2:30–3:20 — Improvement

Explain:

- hybrid retrieval
- metadata/version filter
- reranking
- query rewrite

## 3:20–4:10 — Evaluation

Show baseline vs improved table.

## 4:10–5:00 — Production Considerations

Discuss:

- Entra ID
- ACL filters
- Key Vault
- Application Insights
- private endpoints
- scaling
- caching
- cost optimization

---

# 24. Final Recommended Strategy

1. **Confirm extension / eligibility.**
2. Obtain the supplied document set and test questions.
3. Create Azure resources only for the minimum functional implementation.
4. Keep application/API/UI local unless deployment is specifically required.
5. Implement a simple baseline first.
6. Save baseline metrics.
7. Add hybrid search, metadata, versioning, query rewriting, reranking, and no-answer handling.
8. Re-run the exact same evaluation set.
9. Produce a clear architecture diagram.
10. Keep enterprise-only services mostly architectural rather than provisioned.
11. Use GPT-5.6 Sol heavily for coding and documentation.
12. Personally verify every major implementation path.
13. Be able to explain every architectural decision.
14. Record a concise five-minute demo.
15. Submit repository, architecture diagram, evaluation results, video, and resume.

---

# 25. Key Takeaway

This assignment looks large because it lists many enterprise concerns, but you do **not** need to build a full Azure enterprise platform.

The practical target is:

> **Build one clean, working Azure-based RAG system, intentionally demonstrate a weak baseline, improve it using sound retrieval techniques, measure the improvement, and explain how the design would be hardened for production.**

With aggressive use of GPT-5.6 Sol and other allowed coding assistants, the expected personal effort is approximately:

> **4–7 focused hours**, subject mainly to Azure setup/debugging variability.

The strongest scoring areas are likely to be:

- sound RAG architecture
- hybrid retrieval
- metadata/version handling
- conversational query rewriting
- hallucination control
- evaluation
- debugging methodology
- production security/scaling reasoning
- ability to personally explain the system

The goal should be **not maximum implementation complexity, but maximum defensibility and evaluation quality per hour spent**.
