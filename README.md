# Civil Engineering Project Copilot

An academic, evidence-grounded assistant for a connected Indian structural-steel project. It
combines public official metadata and samples with a clearly labelled synthetic project so RAG,
Graph RAG, and agentic investigation can be demonstrated without pretending that public samples
are a real construction project.

The detailed, plain-language product and architecture proposal is in [PROPOSAL.md](PROPOSAL.md).

## Quick start

```bash
cp .env.example .env
make setup
make services-up
make data-generate
make ingest
make api     # terminal 1
make ui      # terminal 2
```

Run `make help` to see data refresh, validation, re-indexing, evaluation, notebook, security, and
shutdown commands. Normal ingestion is idempotent. The destructive local-index reset requires an
explicit confirmation value.
