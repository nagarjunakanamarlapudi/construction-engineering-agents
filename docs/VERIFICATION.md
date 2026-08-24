# Verification Report

**Verified:** 24 August 2026

**Environment:** macOS host, Python 3.12, Docker Desktop, local PostgreSQL/Qdrant/Neo4j/Langfuse, configured OpenAI and managed Mem0

This file records what was actually executed for the current repository state. It is not a future test plan.

## Results

| Area | Command / check | Result |
|---|---|---|
| Unit/integration/UI/operations contracts | `uv run pytest -q` | 253 passed, 7 live-service tests intentionally skipped in the default run |
| Focused live database integration | `RUN_DATABASE_INTEGRATION=1 uv run pytest tests/integration/test_database_ingestion.py -q` | 1 passed against PostgreSQL, Qdrant, and Neo4j |
| Formatting and lint | `make lint` | Ruff formatting and lint passed |
| Code security | `make security` | Bandit: no issues; pip-audit: no known dependency vulnerabilities |
| Credentials | `make credentials` | OpenAI valid; Mem0 valid; no account data or keys printed |
| Mem0 add/update/restart round trip | Save `citation_detail=compact`, change it to `expanded`, restart the API, and repeat through `/api/memory/reviewer` | Managed Mem0 retained one current memory; PostgreSQL retained one `(user, project, preference type)` mapping; the final read returned `expanded` |
| Durable preference-key integration | `RUN_DATABASE_INTEGRATION=1 uv run pytest -q tests/integration/test_preference_memory_index.py` | 1 passed; a new index instance recovered and updated the same Mem0 ID mapping |
| Data reproducibility | `make data-generate && make data-validate` | 245 records, 245 chunks, 453 relationships, zero dangling links; stable checksums |
| Restart-safe, idempotent ingestion | `make ingest` after an interrupted reindex, then `make ingest` again | Recovered to 333 records, 383 chunks, 333 graph nodes, and 460 relationships; the second run reported every item unchanged |
| Service health | `make health` | PostgreSQL, Qdrant, Neo4j, and Langfuse reachable; required services healthy |
| Docker exposure | Compose inspection | Published data/UI ports bind to `127.0.0.1`; supporting Langfuse stores have no host ports |
| Container build | `docker build -t civil-copilot:verify .` | Successful image build |
| Teaching notebooks | `make notebooks` | All eight notebooks executed first-to-last; Notebook 07 reused production code and ran the IS 800 scenario, while Notebook 08 ran a domain-neutral Mem0 lifecycle in RAM |
| Mem0 primer live modes | Execute Notebook 08 with `MEM0_PRIMER_MODE=oss_openai`, then `MEM0_PRIMER_MODE=platform MEM0_PRIMER_CLEANUP=1` | Both completed with a 100% notebook evaluation rate; the Platform run deleted only the two memories created for its unique demo user |
| Portable end to end | `make e2e` | 47 E2E/notebook/UI/API tests passed and all 7 evaluation scenarios passed |
| Offline evaluation | `make eval` | All 7 scenarios passed |
| Live stack integration | `make e2e-live` | Build, health, idempotent ingest, and 43 integration/E2E/UI/API tests passed (1 skipped); the final live model evaluation did not meet its gate because the configured OpenAI reranker timed out |
| Browser-based standards review | Quality Control Room → Run standards evidence review | Seven readable evidence cards rendered with source labels and the preview limitation; the agent used only `assess_standard_evidence` and returned 19 citations |

## Evaluation summary

| Metric | Offline | Live |
|---|---:|---:|
| Scenario pass rate | 100% | 42.9% |
| Route accuracy | 100% | 100% |
| Citation coverage | 100% | 42.9% |
| Abstention accuracy | 100% | 42.9% |
| Recall at 6 | 75.5% | 16.0% |
| Reciprocal rank | 90.5% | 23.2% |
| Tool-selection precision | 82.1% | 71.4% |
| Unnecessary-step rate | 10.7% | 14.3% |

Machine-readable details are in [`data/evals/report.json`](../data/evals/report.json) and [`data/evals/report-live.json`](../data/evals/report-live.json).

## Data verification

| Data origin | Records | Chunks | Relationships |
|---|---:|---:|---:|
| Official public BIS preview/catalogue corpus | 88 | 138 | 0 |
| `SYNTHETIC — ACADEMIC DEMO` project | 245 | 245 | 453 |
| Explicit exact project-code → BIS-preview links | — | — | 7 |
| Combined searchable corpus | 333 | 383 | 460 |

The public folder also retains four buildingSMART IFC samples and one BCF sample. These technical files are catalogued separately and are not represented as records from the synthetic project.

## Scenario spot checks

- Direct RAG used only `search_documents` for RFI-087 and cited the RFI.
- Graph RAG followed RFI-087 to its connected drawing/activity records.
- Revision investigation connected S-204 Rev 3/Rev 5, RFI-087, and ACT-STEEL-009.
- Quality investigation used `query_quality_records`, `find_graph_paths`, and `get_records`, then cited open NCR-005/NCR-006 and the required repeat inspections.
- The IS 800 evidence comparison used exactly `assess_standard_evidence`, returned seven topic rows and both project/BIS citations, and stated that a public preview cannot prove full compliance.
- An unsupported question triggered the tested abstention path.

## Honest live-evaluation limitation

The standards scenario itself passed in live mode. It routed to one bounded
`assess_standard_evidence` tool call and remained grounded. The complete live evaluation gate did
not pass: all hosted reranker requests exceeded the configured four-second timeout and the current
safe policy is `fail_closed`, so direct-RAG evidence was intentionally not returned. Two unrelated
multi-step live scenarios also selected inefficient tool sequences. These failures are preserved in
`data/evals/report-live.json`; they must not be reported as a successful live quality baseline.

## Known non-blocking warning

The test run reports one upstream Starlette deprecation warning about its current FastAPI `TestClient` compatibility layer. It does not fail tests or affect the application API. Dependency versions are locked and the security audit is clean.
