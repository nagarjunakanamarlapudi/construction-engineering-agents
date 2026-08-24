# Local Operations

This guide starts, refreshes, verifies, and stops the academic Copilot on one development machine.

## Prerequisites

- Docker Desktop
- `uv`
- `make`
- Python 3.12
- an OpenAI API key for live embeddings/model routing
- a Mem0 API key only if preference memory will be demonstrated

## Environment file

```bash
cp .env.example .env
```

Add the two external-service keys:

```text
OPENAI_API_KEY=...
MEM0_API_KEY=...
```

Fill all blank Langfuse and database secrets with strong local values. The populated `.env` is ignored by Git. Do not paste it into issues, screenshots, notebooks, or logs.

### Why local Langfuse still has public and secret keys

Langfuse is self-hosted here, but its ingestion API still authenticates an application to a particular Langfuse project. The public/secret pair is a local project credential created by the Docker initialization settings. It is not a Langfuse Cloud subscription key. The application uses the pair to send traces to <http://127.0.0.1:3000>.

### Mem0 configuration

The current Mem0 SDK scopes the API key to the account/project. Only `MEM0_API_KEY` is required. Legacy organization/project ID variables are intentionally absent.

A preference has one application key: `(user_id, project_id, preference_type)`. PostgreSQL stores the Mem0-generated memory ID for that key. The first save uses Mem0 `add`; changing the same preference uses Mem0 `update`, so the dashboard should show one current memory instead of a new entry for every change. The application supplies the validated key and value with inference disabled; Mem0 does not extract project facts from chat.

## Ports

| Service | Local address / port |
|---|---|
| Streamlit UI | `127.0.0.1:8501` |
| FastAPI | `127.0.0.1:8011` |
| Langfuse | `127.0.0.1:3000` |
| PostgreSQL | `127.0.0.1:55432` |
| Qdrant HTTP / gRPC | `127.0.0.1:6333` / `6334` |
| Neo4j Browser / Bolt | `127.0.0.1:7474` / `7687` |

PostgreSQL uses port 55432 so it does not collide with the common local port 5432.

## First startup

```bash
make setup
make services-up
make observability-up
make data-download
make data-generate
make data-validate
make ingest
make health
make credentials
```

`data-download` refreshes only permitted public sources. It does not silently fetch or relabel a complete Indian Standard.

Run the API and UI in separate terminals:

```bash
make api
```

```bash
make ui
```

## Data and indexing commands

| Command | Use |
|---|---|
| `make data-download` | Refresh permitted public source files |
| `make data-generate` | Rebuild the same deterministic synthetic project |
| `make data-validate` | Check checksums, fields, revisions, provenance, and relationships |
| `make data-status` | Show corpus and index counts |
| `make ingest` | Insert/update changed data; safe to repeat |
| `make reindex` | Rebuild Qdrant and Neo4j from authoritative data |
| `make reindex-docs` | Rebuild only the Qdrant document index |
| `make reindex-graph` | Rebuild only the Neo4j graph |
| `make reset-indexes CONFIRM=reset-local-indexes` | Destructively clear local indexes; explicit confirmation required |

Normal refreshes should use `make ingest` or the safe reindex commands. The reset target exists only for disposable local development data.

## Verification commands

```bash
make test
make lint
make security
make eval
make eval-live
make notebooks
```

- `make eval` is reproducible and can run without external model calls.
- `make eval-live` uses configured OpenAI, Qdrant, Neo4j, Mem0 policy, and Langfuse tracing.
- `make notebooks` executes all eight teaching notebooks headlessly. Notebooks 01–07 explain and exercise the Civil Engineering Project Copilot; Notebook 08 is a separate, domain-neutral Mem0 primer.

## Shutdown

Stop the API and UI with `Ctrl-C`, then run:

```bash
make observability-down
make services-down
```

Docker volumes are retained. Shutdown does not delete project data or traces.

## Troubleshooting

**`make health` cannot reach a service**  
Run `docker compose ps` and `docker compose -f compose.observability.yaml ps`. Wait for health checks, then retry.

**The UI opens but chat fails**  
Confirm the API is running at <http://127.0.0.1:8011/health>. The application uses `127.0.0.1` intentionally to avoid a local IPv6 `localhost` conflict and port `8011` to avoid the existing DynamoDB service on `8001`.

**Mem0 dashboard shows zero memories**  
Save an allowlisted preference in the UI, select the correct Mem0 project, and refresh. Project facts are rejected by policy, so normal RAG answers do not create memories.

**Langfuse has no traces**  
Confirm its public/secret keys in `.env` match the local initialization values and that `LANGFUSE_BASE_URL=http://127.0.0.1:3000`.

**A re-run duplicates data**  
This is a defect: ingestion is designed to be idempotent. Run `make data-status`, preserve the output, and use the test suite before resetting indexes.
