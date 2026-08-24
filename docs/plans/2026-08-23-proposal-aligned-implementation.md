# Proposal-Aligned Implementation Plan

## Specification

`PROPOSAL.md` and its original architecture images are the binding product and architecture contract.

## Global constraints

- Do not simplify or redraw the target architecture to match incomplete code.
- The online local/live runtime must read PostgreSQL, Qdrant, and Neo4j; portable in-memory behavior is an explicit mode, never a silent fallback.
- Compound investigations use a genuine observation-driven ReAct loop. The model chooses the next registered tool after observing the previous result.
- Every agent-callable capability is a typed LangChain `@tool` registered in one central registry.
- Project/user/permission context is injected at runtime and hidden from model-controlled tool arguments.
- Tools are read-only, bounded, permission-aware, observable, and return structured observations with evidence, citations, status/errors, confidence, and elapsed time.
- RAG-gated tool selection is backlog only; do not implement it in this plan.
- Mem0 stores approved preferences only; project facts come from fresh retrieval.
- The application and production-mirror notebook use the same public runtime factory and production modules.
- The educational notebook is visibly labelled as a toy and does not represent deployed behavior.
- Use test-driven development: add a failing behavior test, verify the intended failure, implement minimally, and re-run relevant and full checks.
- Preserve public-versus-synthetic provenance labels and never expose secret values.

## Task 1: Live data and retrieval runtime

Implement explicit execution modes and reader ports/adapters so local/live online queries use PostgreSQL for records, Qdrant for filtered hybrid retrieval, and Neo4j for bounded graph traversal. Preserve portable implementations for tests and teaching. Add a shared runtime/capability factory used by API and notebooks. Add focused unit/integration tests.

## Task 2: LangChain tools and bounded ReAct orchestration

Create dedicated Pydantic input/output models, LangChain `@tool` functions, a central tool registry, runtime context injection, read-only execution envelope, deterministic schedule/calculator services, specialist tool sets, and a genuine bounded `create_agent`/LangGraph ReAct flow. Add structured stop reasons, streaming-friendly trace events, checkpoints, Langfuse integration points, and agent/tool evals. Add focused tests.

## Task 3: Educational notebook

Create `notebooks/06_educational_toy_end_to_end.ipynb`, a self-contained, no-network, no-credentials teaching implementation that visibly demonstrates correlated data, indexing, exact/sparse/dense retrieval, fusion, reranking, Fast RAG, Graph RAG, typed tools, bounded ReAct, memory, citations, abstention, and evals with two examples. Mark it `EDUCATIONAL TOY — NOT PRODUCTION` in metadata and visible cells.

## Task 4: Production-mirror notebook

Create `notebooks/07_production_mirror_end_to_end.ipynb` as a thin control surface over the same runtime factory, stores, retrievers, registered tools, ReAct workflow, memory, tracing, and evals used by FastAPI/Streamlit. It must contain no duplicate production business logic. Add notebook contract and headless execution tests.

## Task 5: Composition, UI, operations, and documentation alignment

Move FastAPI and Streamlit to the shared runtime, expose progress/tool/observation/stop/citation data without hidden chain-of-thought, align Docker Compose and Make targets, and add a machine-derived capability/status section. Keep target diagrams intact; update status prose only after verified implementation.

## Task 6: End-to-end verification

Run services and idempotent indexing twice, prove live reads from all three stores, run Fast RAG/Graph RAG/ReAct scenarios, exercise Mem0 and Langfuse when configured, execute both notebooks, run eval/security/lint/test suites, and visually inspect the Streamlit demo.
