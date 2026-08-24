# Proposal Image Set

The master [proposal](../../PROPOSAL.md) uses the images in this directory to explain the academic pilot, its data boundaries, and the remaining production extensions. Diagrams describe working components directly; only genuinely unfinished production breadth is labelled as future.

## Status and provenance figures

| File | Purpose |
|---|---|
| `data-provenance-landscape.png` | Authoritative picture of public/downloaded, public/link-only, synthetic academic, and future authorized-project data |
| `searchable-evidence-pipeline.png` | Shows the synthetic/public-preview inputs, PostgreSQL/Qdrant/Neo4j indexes, RAG/Graph RAG/ReAct use, and the Mem0 boundary |
| `mockup-data-library.png` | Early interface concept for inspecting source, content boundary, academic-use label, and project applicability |
| `mockup-evidence-answer.png` | Early interface concept for a direct-RAG answer with evidence and no agent loop |

### Visual truth rules

- **Data origin:** blue = public downloaded; gray = public link-only; orange = synthetic academic demo; purple = future authorized project data.
- BIS pages are labelled **Indian codes and standards — official public previews**. A preview is never presented as the complete standard unless explicitly verified.
- “Synthetic” means fictional academic records deliberately created as one internally consistent project. It does not describe public data.
- Architecture diagrams describe the working academic pilot. Captions call out production-only additions where relevant.

## Detailed architecture discussion set

| File | Purpose |
|---|---|
| `civil-copilot-architecture-overview.png` | Separate the offline data plane from the online question plane and show the simple and compound routes |
| `data-ingestion-architecture.png` | Explain how source records become trusted, versioned project knowledge |
| `data-retrieval-architecture.png` | Explain how a scoped question becomes a permission-filtered evidence packet and cited answer |
| `agent-orchestration-architecture.png` | Distinguish deterministic routing, Fast RAG, bounded agents, memory, and guardrails |
| `tools-architecture.png` | Distinguish agent reasoning from typed, permission-aware tool execution |

## Plain-language submission set

These four images provide plain-language views for readers who may know neither construction nor artificial intelligence.

| File | Purpose |
|---|---|
| `submission-capability-overview.png` | Show direct evidence search, connected project records, ReAct investigation, and standards-evidence review without status badges |
| `submission-system-architecture.png` | Explain how information preparation differs from question answering and show the direct and multi-step paths |
| `submission-question-routing.png` | Compare one direct evidence search with a controlled multi-step investigation and define RAG and Agentic RAG |
| `component-responsibility-map.png` | Give data preparation, RAG, Graph RAG, approved tools, ReAct agents, Mem0, and source stores one clear responsibility each |

The full prompts and shared art direction are recorded in [Submission Proposal — Diagram Prompts](submission-visual-prompts.md).

### Submission-set visual language

- Blue: collecting and preparing information
- Green: search and supporting evidence
- Purple: bounded ReAct investigation
- Orange: approved lookups, comparisons, and calculations
- Gray: stored information, evidence, and safeguards
- Teal: approved preferences and conversation context

### Submission-set generation mode

The four images were generated with the built-in image-generation tool in infographic-diagram mode. Selected images were edited through the same tool to correct arrow meaning, preserve the memory boundary, and ensure a solid white background. Final files were visually reviewed before being placed in this directory.

## Data-boundary and mockup generation prompts

The images were generated with the built-in image-generation tool and visually checked before being copied into this directory.

### Data provenance landscape

> Create a 16:9 hand-drawn whiteboard infographic titled “What Data Do We Have — and What Is Still Planned?” Separate four columns: PUBLIC — DOWNLOADED, PUBLIC — LINK ONLY, SYNTHETIC — PLANNED, and REAL PROJECT — FUTURE. Show the exact current counts for four IFC files, one BCF sample, 88 BIS preview records, and 138 prepared JSONL chunks. Mark BIS as “INDIAN CODES & STANDARDS — OFFICIAL PUBLIC PREVIEWS” and warn that preview/metadata is not necessarily the full standard. Do not show architecture components.

### Searchable evidence pipeline

> Create a 16:9 hand-drawn whiteboard infographic titled “How Project Information Becomes Searchable Evidence.” Show 245 synthetic project records, 88 official BIS public-preview records, 138 official BIS public-preview chunks, preserved IFC/BCF samples, and clear origin labels. Flow into PostgreSQL with 333 structured records, Qdrant with 383 searchable chunks, Neo4j with 333 nodes and 460 relationships, plus source files/checksums/manifests. Flow into RAG, Graph RAG, ReAct agents, and cited answers. Show Mem0 in a separate card for approved display/routing preferences only, never project facts. Do not use implementation-status badges.

### Data-library product mockup

> Create a 16:9 hand-drawn web-dashboard concept titled “Civil Engineering Project Copilot — Data Library.” Show the four data-origin categories and an IS 800 source card labelled Indian code of practice, Bureau of Indian Standards, official public preview, academic/non-commercial, content not confirmed as the full standard, and project applicability not yet approved.

### Evidence-answer product mockup

> Create a 16:9 hand-drawn application concept titled “Civil Engineering Project Copilot — Evidence Answer.” Show a direct-RAG answer for fictional drawing S-204 Revision 5, two fictional evidence records, an explicit synthetic-data warning, the exact-search/status-filter trace, and “No agent needed.”

## Generation mode

The images were produced with the built-in image-generation tool. The supplied screenshot was used only as a style reference.

## Shared prompt

> Create a polished 16:9 hand-drawn technical whiteboard infographic for the Civil Engineering Project Copilot. Use a clean white background, rounded framed zones, friendly marker line art, short readable labels, generous whitespace, civil-project icons, and accurate directional arrows. Use blue for ingestion, green for retrieval, purple for agents, orange for tools, and gray for stores, evidence, and cross-cutting controls. Do not use logos, vendor mascots, watermarks, or long paragraphs.

## Asset-specific prompts

### System overview

> Show two unmistakably separate planes. The offline data plane moves Project Sources through Connect + Sync, Parse / OCR, Normalize + Version, and Chunk + Enrich into Controlled Source Files, Qdrant, PostgreSQL, and Neo4j. The online question plane moves User Question into a deterministic Query Router. Simple questions use Fast RAG and Data Retrieval. Compound questions use a Copilot Orchestrator with Document, Schedule, and Risk agents; those agents call permission-aware Search, Record, Graph, Schedule, Compare, and Calculate tools. Both paths use access-filtered retrieval to build an Evidence Packet and Cited Answer. Show managed Mem0 as approved preferences only, never project truth. Add the rule: “Agents choose. Tools execute. Retrieval builds evidence.”

### Data ingestion

> Show a left-to-right offline write path with five stages: Sources, Acquire, Understand, Enrich, and Publish. Include project document types, API/export/webhook/file-drop acquisition, parsing/OCR/table extraction/classification/metadata/revision tracking, document-aware chunks/embeddings/entities/ACL provenance, a validation queue, and the four approved target stores: Source Files, Qdrant, PostgreSQL, and Neo4j. Label the design “APPROVED TARGET — NOT IMPLEMENTED.” End with the lineage example RFI-087 → response → Drawing M-412 Rev 4 → Activity MEP-420 and the rule that every chunk and graph edge keeps its source.

### Data retrieval

> Show how “Why is Level 4 HVAC delayed?” becomes evidence through six stages: Understand, Enforce, Retrieve, Improve, Build Context, and Answer. Run Qdrant Exact + Full Text, Qdrant Dense Search, Neo4j Graph Traversal, and PostgreSQL Structured Records in parallel after ACL and metadata filtering; then rank-fuse, cross-encoder rerank, deduplicate, and build an Evidence Packet containing passages, records/calculations, graph paths, and citations/provenance. Distinguish deterministic Fast RAG from a compound question that requests several retrieval tools. End with grounded facts, calculations, inferences, citations, and abstention when evidence is missing.

### Agent orchestration

> Show a deterministic Query Router splitting simple and compound questions. The simple path is Fast RAG → Evidence Packet → Cited Answer with no agent loop. The compound path uses a Copilot Orchestrator with LangGraph state and a bounded PLAN → ACT → OBSERVE → DECIDE loop. It may delegate to Document, Schedule, and Risk agents, which call permission-aware tools and return observations. Show working state, Mem0 approved memory, fresh retrieval as truth, and guardrails for steps, time/cost, read-only tools, ACLs, abstention, and human review. Emphasize: “Agents reason and choose. Tools execute and return observations.”

### Tools

> Show Agent Tool Request → Validate Input + Enforce ACL → Toolbox → Structured Observation → Back to Agent. The toolbox contains Search Docs/Qdrant, Get Record/PostgreSQL, Graph Traverse/Neo4j, Schedule Impact/Schedule Service, Compare Revisions/Source Files, Calculator/No LLM, and Standards Evidence/Project + BIS public preview. Observations return result data, source IDs, citations, confidence/errors, and elapsed time. Mark the toolbox as read-only. Future writes require preview, human approval, and an audit log. Emphasize: “Agents decide what to do. Tools do the work.”
