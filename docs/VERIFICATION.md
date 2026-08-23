# Verification Report

**Verified:** 23 August 2026

**Environment:** macOS host, Python 3.12, Docker Desktop, local PostgreSQL/Qdrant/Neo4j/Langfuse, configured OpenAI and managed Mem0

This file records what was actually executed for the current repository state. It is not a future test plan.

## Results

| Area | Command / check | Result |
|---|---|---|
| Unit/integration/UI/operations contracts | `make test` | 60 passed, 1 database-service test intentionally skipped in the default run |
| Live database integration | `RUN_DATABASE_INTEGRATION=1 uv run pytest tests/integration/test_database_ingestion.py -q` | 1 passed against PostgreSQL, Qdrant, and Neo4j |
| Formatting and lint | `make lint` | Ruff formatting and lint passed |
| Code security | `make security` | Bandit: no issues; pip-audit: no known dependency vulnerabilities |
| Credentials | `make credentials` | OpenAI valid; Mem0 valid; no account data or keys printed |
| Mem0 application round trip | POST then GET `/api/memory/final-mem0-validation` | Saved and loaded allowlisted `citation_detail=expanded` through managed Mem0 |
| Data reproducibility | `make data-generate && make data-validate` | 245 records, 245 chunks, 453 relationships, zero dangling links; stable checksums |
| Idempotent ingestion | `make ingest` twice | Both runs: 333 records, 383 chunks, 333 graph nodes, and 453 relationships unchanged; zero duplicates/updates |
| Service health | `make health` | PostgreSQL, Qdrant, Neo4j, and Langfuse reachable; required services healthy |
| Docker exposure | Compose inspection | Published data/UI ports bind to `127.0.0.1`; supporting Langfuse stores have no host ports |
| Container build | `docker build -t civil-copilot:verify .` | Successful image build |
| Teaching notebooks | `make notebooks` | All five notebooks executed headlessly using production modules |
| Offline evaluation | `make eval` | All 6 scenarios passed |
| Live evaluation | `make eval-live` | All 6 scenarios passed using configured live services |
| Browser-based UI review | Four modes plus grounded chat trace | Chat, impact, revision, and quality screens loaded; scenarios returned routes/tools/evidence; current screenshots saved |

## Evaluation summary

| Metric | Offline | Live |
|---|---:|---:|
| Scenario pass rate | 100% | 100% |
| Route accuracy | 100% | 100% |
| Citation coverage | 100% | 100% |
| Abstention accuracy | 100% | 100% |
| Recall at 6 | 84.7% | 80.6% |
| Reciprocal rank | 87.5% | 87.5% |
| Tool-selection precision | 95.8% | 95.8% |
| Unnecessary-step rate | 4.2% | 4.2% |

Machine-readable details are in [`data/evals/report.json`](../data/evals/report.json) and [`data/evals/report-live.json`](../data/evals/report-live.json).

## Data verification

| Data origin | Records | Chunks | Relationships |
|---|---:|---:|---:|
| Official public BIS preview/catalogue corpus | 88 | 138 | 0 |
| `SYNTHETIC — ACADEMIC DEMO` project | 245 | 245 | 453 |
| Combined searchable corpus | 333 | 383 | 453 |

The public folder also retains four buildingSMART IFC samples and one BCF sample. These technical files are catalogued separately and are not represented as records from the synthetic project.

## Scenario spot checks

- Direct RAG used only `search_documents` for RFI-087 and cited the RFI.
- Graph RAG followed RFI-087 to its connected drawing/activity records.
- Revision investigation connected S-204 Rev 3/Rev 5, RFI-087, and ACT-STEEL-009.
- Quality investigation used `query_quality_records`, `find_graph_paths`, and `get_records`, then cited open NCR-005/NCR-006 and the required repeat inspections.
- An unsupported question triggered the tested abstention path.

## Known non-blocking warning

The test run reports one upstream Starlette deprecation warning about its current FastAPI `TestClient` compatibility layer. It does not fail tests or affect the application API. Dependency versions are locked and the security audit is clean.
