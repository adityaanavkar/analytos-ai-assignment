# Architecture Diagram Presentation Talk Track

Use this script while displaying `production-azure-rag.png`.

The architecture section should take approximately two minutes.

## Opening

"This diagram shows the proposed production architecture for the Enterprise Knowledge Assistant.
I have separated it into three areas: the online question-answering path, the asynchronous document-ingestion path, and the production controls that support both."

## 1. Start with the user

"Starting from the top-left, an employee opens the chat interface and signs in through Microsoft Entra ID.
Azure Front Door and the Web Application Firewall provide the protected internet entry point.
Entra ID supplies trusted department and group claims, such as whether the employee belongs to Engineering, Finance, or HR."

## 2. Explain the application layer

"The authenticated request reaches the Python FastAPI application hosted on Azure App Service.
The application rewrites conversational follow-up questions, detects ambiguity, and prepares one or more retrieval queries.
It also converts the trusted identity claims into an access-control filter.
The client cannot supply or override this filter directly."

## 3. Explain access-controlled retrieval

"Azure AI Search performs hybrid retrieval using keyword search, vector similarity, and semantic ranking.
The important security control is that the `allowed_groups` filter is applied inside Azure AI Search.
This means an Engineering user cannot retrieve an HR chunk, and unauthorized content never reaches the language model."

## 4. Explain grounded generation

"The application selects a small, relevant evidence set and sends only that evidence to Azure OpenAI.
Azure OpenAI produces a concise answer using the supplied context.
Before returning the answer, the application checks evidence sufficiency and validates every citation against an actually retrieved chunk.
If the evidence is missing or a citation is invalid, the application returns a safe refusal instead of guessing."

## 5. Explain document ingestion

"The second lane shows the ingestion pipeline, which runs independently of user questions.
Approved PDF, Word, and Excel documents are stored in Azure Blob Storage.
An event-driven Azure Functions worker validates each document, parses its structure, and creates deterministic chunks.
Each chunk receives source provenance, version information, effective dates, department metadata, and allowed groups.
Azure OpenAI creates embeddings, and the pipeline reconciles the resulting chunks into Azure AI Search without duplicating unchanged content."

## 6. Explain production controls

"The bottom lane contains the production controls.
Managed identities and Key Vault prevent secrets from being stored in application code.
Private endpoints and VNet integration reduce public network exposure.
Application Insights and Log Analytics record latency, failures, retrieval behavior, and operational alerts without logging sensitive document content.
Autoscaling, queues, retries, caching, budgets, quotas, bounded retrieval, and token limits support reliability and cost control."

## 7. State the current implementation honestly

"The current working demo runs the browser interface and FastAPI application locally while using Azure OpenAI, Azure AI Search, Blob Storage, Application Insights, and Log Analytics in Azure.
App Service hosting, Entra application authentication, private endpoints, Key Vault integration, and retrieval-time department enforcement are the production target shown here.
I have intentionally separated the working demo from the proposed production architecture so that the submission does not overstate what has already been deployed."

## Closing transition

"The main design principle is that identity controls retrieval before generation, and evidence validation controls the answer before it reaches the user.
Next, I will demonstrate the working chatbot and show how the improved RAG pipeline performs against the baseline."

## Short version if time is running out

"Employees authenticate through Entra ID and reach the FastAPI application through protected Azure ingress.
The application converts trusted group claims into an Azure AI Search filter, performs hybrid retrieval, and sends only authorized evidence to Azure OpenAI.
Every answer is checked for sufficient evidence and valid citations before being returned.
Documents are ingested asynchronously from Blob Storage with structure, provenance, version, and access metadata.
Managed identity, Key Vault, private networking, monitoring, autoscaling, and cost controls complete the proposed production design.
The current demo uses local application hosting with live Azure AI services, while the remaining hosting and security components are the production target."

## Likely reviewer questions

### Why Azure AI Search?

"Azure AI Search provides keyword, vector, semantic, metadata-filtering, and scaling capabilities in one managed retrieval service.
It also allows the access-control filter to execute during retrieval instead of filtering sensitive results afterward."

### Why hybrid retrieval?

"Vector search handles semantic similarity, while keyword search preserves exact terms such as policy names, prices, identifiers, and URLs.
Semantic ranking then improves the ordering of the combined candidate set."

### How does this prevent Engineering users from seeing HR documents?

"The application derives groups from validated Entra claims and creates an `allowed_groups` filter inside Azure AI Search.
Because the filter is applied before chunks are returned, HR text cannot enter the model prompt for an unauthorized Engineering user."

### How would this scale to millions of documents?

"I would use distributed queue-based ingestion, batch embeddings, incremental content-hash processing, additional Search partitions for index capacity, replicas for query throughput, and controlled index sharding where tenant or regulatory isolation requires it."

### How do you control cost?

"I bound the retrieved context, generation tokens, and query decomposition, skip unchanged documents, batch embeddings, cache only with access-aware keys, and monitor token usage and Azure budgets through alerts."

