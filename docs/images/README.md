# Current Project Images

This directory contains only visuals that describe the implemented academic pilot. The master [proposal](../../PROPOSAL.md) uses relative image paths so it renders correctly in the repository viewer.

## Architecture explainers

| File | Purpose |
|---|---|
| `civil-copilot-current-architecture.png` | Separates data ingestion, data retrieval, agents, tools/answers, memory, and observability |
| `data-provenance-current.png` | Separates public official inputs from the connected synthetic academic project and shows current counts |
| `question-routing-current.png` | Compares Direct RAG, Graph RAG, and bounded Agentic RAG with example questions |

The explainers use a hand-drawn style for broad audiences. Exact technical details are also stated in text and tables in the proposal. The images were generated with the built-in image-generation tool and visually checked for factual boundaries and legibility.

## Real application screenshots

| File | Purpose |
|---|---|
| `screenshots/01-copilot-home.png` | Copilot Chat home and guided scenarios |
| `screenshots/02-impact-explorer.png` | Relationship-path explorer |
| `screenshots/03-revision-evidence-lab.png` | Drawing revision comparison experience |
| `screenshots/04-quality-control-room.png` | Inspection and NCR investigation experience |
| `screenshots/05-grounded-chat-trace.png` | Visible route, bounded plan, and tool trace from a live answer |

These screenshots were captured from the running local application after browser-based checks. They are not speculative mockups.

## Truth rules used by every image

- Orange means `SYNTHETIC — ACADEMIC DEMO`.
- Public BIS material is described as catalogue/public-preview content, not complete Indian Standards text.
- PostgreSQL, Qdrant, Neo4j, and Langfuse are local Docker services.
- OpenAI and managed Mem0 are external service boundaries.
- Mem0 stores approved user preferences only.
- The tool set is read-only and a human remains responsible for engineering decisions.
