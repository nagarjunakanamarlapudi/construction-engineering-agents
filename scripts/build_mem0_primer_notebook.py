"""Build the domain-neutral Mem0 teaching notebook from readable percent cells."""

from __future__ import annotations

from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "notebooks" / "08_mem0_primer.ipynb"

SOURCE = r"""# %% [markdown]
# 08 — Mem0 Primer: Memory for AI Applications

> **DOMAIN-NEUTRAL PRIMER:** This notebook explains Mem0 independently of any particular business domain. It is meant for evaluating Mem0 for assistants, tutors, support systems, productivity tools, recommendation systems, and other AI applications.

You will see both the mental model and executable examples. The default **offline** path uses the real Mem0 OSS library with Qdrant vectors and SQLite history held in RAM. It needs no credentials and loses its contents when the kernel stops.

# %% [markdown]
## What Mem0 is

![What Mem0 is and is not](../docs/images/mem0-primer-mental-model.png)

Mem0 is a **long-term memory layer for AI applications**. It helps an application retain useful context—such as preferences, stable facts, past outcomes, goals, and constraints—and retrieve only the memories relevant to a later request.

A memory is smaller and more deliberate than a complete chat transcript. Each stored item receives a unique **memory ID**, searchable text, an embedding, metadata, timestamps, and one or more entity scopes.

# %% [markdown]
## What Mem0 is not

Mem0 does **not** replace:

- **Chat history:** recent messages kept in order for conversational continuity.
- **Working state:** temporary tool results, intermediate calculations, or workflow checkpoints.
- **RAG knowledge base:** indexed documents and authoritative reference material.
- **Source-of-truth database:** accounts, permissions, balances, orders, policies, or other governed records.
- **Authorization:** memory retrieval must still be scoped by trusted server-side identity.

A useful rule: **RAG answers “what do our sources say?”; memory answers “what useful context should this application remember?”**

# %% [markdown]
## What you will learn

1. How Mem0 extracts memories with `infer=True`.
2. How an application stores validated values with `infer=False`.
3. Why **Hybrid ownership** is usually the safest production design.
4. How `user_id`, `agent_id`, `app_id`, and `run_id` partition memory.
5. How add, search, get, update, history, and delete form the memory lifecycle.
6. How to run Mem0 in notebook RAM, with local models, or on Mem0 Platform.
7. How to perform Evaluation of extraction, retrieval, isolation, freshness, and deletion.
8. Privacy and governance boundaries that should exist before production use.

# %% [markdown]
## Three deployment modes

![Three practical ways to run Mem0](../docs/images/mem0-primer-deployment-modes.png)

This notebook supports four execution values:

| `MEM0_PRIMER_MODE` | Storage | Extraction and embeddings | Required service |
|---|---|---|---|
| `offline` | Mem0 OSS in RAM | Direct storage plus deterministic teaching embeddings | Nothing |
| `oss_openai` | Mem0 OSS in RAM | OpenAI | `OPENAI_API_KEY` |
| `oss_ollama` | Mem0 OSS in RAM | Ollama | Local Ollama server and models |
| `platform` | Mem0 Platform | Managed Mem0 extraction and storage | `MEM0_API_KEY` |

The default is `offline`, even when keys exist. Select a live path explicitly before running all cells:

```bash
MEM0_PRIMER_MODE=oss_openai uv run jupyter lab
# or: MEM0_PRIMER_MODE=platform uv run jupyter lab
```

Set `MEM0_PRIMER_LOAD_DOTENV=0` when you intentionally do not want the notebook to read the repository's `.env`.

# %%
from __future__ import annotations

import html
import json
import logging
import os
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path.cwd()
if not (ROOT / "pyproject.toml").exists():
    ROOT = ROOT.parent

LOAD_DOTENV = os.getenv("MEM0_PRIMER_LOAD_DOTENV", "1") == "1"
if LOAD_DOTENV:
    load_dotenv(ROOT / ".env", override=False)

# Keep this isolated teaching notebook from emitting OSS product telemetry.
os.environ.setdefault("MEM0_TELEMETRY", "False")
logging.getLogger("mem0").setLevel(logging.ERROR)

from IPython.display import HTML, Markdown, display
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from mem0 import Memory, MemoryClient
from qdrant_client import QdrantClient

VALID_MODES = {"offline", "oss_openai", "oss_ollama", "platform"}
MODE = os.getenv("MEM0_PRIMER_MODE", "offline").strip().lower()
if MODE not in VALID_MODES:
    raise ValueError(f"MEM0_PRIMER_MODE must be one of {sorted(VALID_MODES)}, got {MODE!r}")

HAS_OPENAI_KEY = bool(os.getenv("OPENAI_API_KEY"))
HAS_MEM0_KEY = bool(os.getenv("MEM0_API_KEY"))
if MODE == "oss_openai" and not HAS_OPENAI_KEY:
    raise RuntimeError("oss_openai mode requires OPENAI_API_KEY in the environment or .env")
if MODE == "platform" and not HAS_MEM0_KEY:
    raise RuntimeError("platform mode requires MEM0_API_KEY in the environment or .env")

print(
    f"mode={MODE} mem0ai={version('mem0ai')} "
    f"openai_key_configured={HAS_OPENAI_KEY} mem0_key_configured={HAS_MEM0_KEY}"
)

# %%
def show_json(title: str, payload: Any) -> None:
    safe = html.escape(json.dumps(payload, indent=2, default=str))
    display(
        HTML(
            f"<div style='border:1px solid #d8d5f2;border-radius:14px;padding:14px;"
            f"margin:8px 0;background:#faf9ff'><b>{html.escape(title)}</b>"
            f"<pre style='white-space:pre-wrap;margin:10px 0 0'>{safe}</pre></div>"
        )
    )


def show_rows(title: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    headers = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(
            f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in fields
        ) + "</tr>"
    display(
        HTML(
            f"<h4>{html.escape(title)}</h4><div style='overflow-x:auto'>"
            f"<table style='border-collapse:collapse;width:100%'>"
            f"<thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div>"
            "<style>th,td{border:1px solid #ddd;padding:8px;text-align:left}"
            "th{background:#ede9fe}</style>"
        )
    )


def rows_from(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        rows = response.get("results", [])
        return rows if isinstance(rows, list) else []
    return response if isinstance(response, list) else []


def added_memory_id(response: Any) -> str:
    for row in rows_from(response):
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            return row["id"]
    if isinstance(response, dict) and isinstance(response.get("id"), str):
        return response["id"]
    raise RuntimeError("The add response did not include a memory ID")

# %%
display(
    HTML(
        "<div style='display:flex;gap:12px;flex-wrap:wrap'>"
        f"<div style='padding:12px 18px;border-radius:999px;background:#ede9fe'>"
        f"<b>Selected mode:</b> {html.escape(MODE)}</div>"
        f"<div style='padding:12px 18px;border-radius:999px;background:#dcfce7'>"
        f"<b>Mem0 version:</b> {html.escape(version('mem0ai'))}</div>"
        "<div style='padding:12px 18px;border-radius:999px;background:#e0f2fe'>"
        "<b>Secrets:</b> loaded but never displayed</div></div>"
    )
)

# %% [markdown]
## Three memory ownership strategies

![Three ways to decide what becomes memory](../docs/images/mem0-primer-three-strategies.png)

### 1. Mem0 decides — `infer=True`

Send conversation messages. An extraction LLM selects durable facts and preferences. This is flexible, but extraction quality must be evaluated on your own conversations.

### 2. Application decides — `infer=False`

Your application validates a known value and asks Mem0 to store it exactly. There is no extraction LLM call. This is appropriate for controlled preferences such as response style, locale, or units.

### 3. Hybrid ownership

Let Mem0 infer soft, conversational context while the application owns hard rules and deterministic settings. Do not let an inference model become the authority for permissions, money, compliance state, or other governed data.

# %% [markdown]
## What happens during extraction?

With `infer=True`:

1. Your application sends one or more conversation messages.
2. The extraction LLM identifies details worth remembering.
3. Mem0 turns each selected memory into an embedding.
4. Text, vector, metadata, timestamps, entity scope, and a memory ID are stored.
5. Later, Mem0 embeds a search question and returns the most relevant scoped memories.

With `infer=False`, step 2 is skipped. The supplied text is stored directly. Semantic search still needs an embedding model.

**Important:** in-memory storage does not mean the extraction model is local. The `oss_openai` mode stores data in notebook RAM while calling OpenAI for extraction and embeddings. The `oss_ollama` mode keeps both inference and storage local.

# %%
def build_in_memory_oss(mode: str) -> Memory:
    qdrant = QdrantClient(location=":memory:")

    if mode == "offline":
        dimensions = 32
        llm = {
            "provider": "langchain",
            "config": {"model": FakeListChatModel(responses=["unused in infer=False mode"])},
        }
        embedder = {
            "provider": "langchain",
            "config": {"model": DeterministicFakeEmbedding(size=dimensions)},
        }
    elif mode == "oss_openai":
        dimensions = 1536
        llm = {
            "provider": "openai",
            "config": {
                "model": "gpt-5-mini",
                "is_reasoning_model": True,
                "reasoning_effort": "low",
            },
        }
        embedder = {
            "provider": "openai",
            "config": {"model": "text-embedding-3-small"},
        }
    elif mode == "oss_ollama":
        dimensions = 768
        llm = {
            "provider": "ollama",
            "config": {"model": "llama3.1:8b", "temperature": 0.0},
        }
        embedder = {
            "provider": "ollama",
            "config": {"model": "nomic-embed-text"},
        }
    else:
        raise ValueError(f"{mode!r} is not an OSS mode")

    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": f"mem0_primer_{mode}_{uuid4().hex[:8]}",
                "embedding_model_dims": dimensions,
                "client": qdrant,
            },
        },
        "llm": llm,
        "embedder": embedder,
        "history_db_path": ":memory:",
    }
    return Memory.from_config(config)


# This always creates a real, credential-free Mem0 OSS lab for the CRUD walkthrough.
lab_memory = build_in_memory_oss("offline")
print("offline_lab_backend=mem0_oss_qdrant_ram history=sqlite_ram")

# %% [markdown]
## The complete memory lifecycle

![The Mem0 memory lifecycle](../docs/images/mem0-primer-lifecycle.png)

The next cells execute this lifecycle against the real Mem0 OSS API. They deliberately use `infer=False` so that the storage, identity, update, history, and deletion behavior is deterministic and easy to inspect.

# %% [markdown]
### 1. Add a controlled memory

The application has already validated the preference. It stores one exact sentence and receives a generated memory ID.

# %%
LAB_USER = "primer-user"
LAB_OTHER_USER = "primer-other-user"
LAB_METADATA = {
    "memory_kind": "preference",
    "preference_type": "answer_style",
    "source": "mem0_primer",
}

add_response = lab_memory.add(
    "Preference answer_style: concise",
    user_id=LAB_USER,
    metadata={**LAB_METADATA, "preference_value": "concise"},
    infer=False,
)
memory_id = added_memory_id(add_response)
show_json("Add response — the ID is the handle for future maintenance", add_response)

# %% [markdown]
### 2. List, retrieve, and search

- **List/get-all** answers “which memories exist in this scope?”
- **Get by ID** returns one known memory.
- **Search** answers “which scoped memories are relevant to this question?”

# %%
listed_before_update = lab_memory.get_all(filters={"user_id": LAB_USER})
listed_rows = rows_from(listed_before_update)
record_before_update = lab_memory.get(memory_id)
search_before_update = lab_memory.search(
    "How should responses be written?",
    filters={"user_id": LAB_USER},
)

show_rows("Memories for primer-user", listed_rows, ["id", "memory", "user_id", "created_at"])
show_rows(
    "Semantic search results",
    rows_from(search_before_update),
    ["id", "memory", "score", "user_id"],
)

# %% [markdown]
### 3. Update by memory ID

A Mem0 memory ID behaves like the record identifier for that stored memory. It is **not automatically your application's business key**.

For a setting such as `(tenant_id, user_id, preference_type)`, keep a durable mapping from that composite business key to the Mem0 memory ID. When the setting changes, call `update` with the same memory ID instead of appending another preference.

# %%
first_memory_id = memory_id
update_response = lab_memory.update(
    memory_id,
    text="Preference answer_style: detailed",
)
record_after_update = lab_memory.get(memory_id)
same_id_after_update = record_after_update["id"] == first_memory_id

show_json("Update response", update_response)
show_json("Memory after update — same ID, new value", record_after_update)

# %% [markdown]
### 4. Inspect history

History is useful for debugging, user-facing corrections, and audits. It does not replace your application's own governed audit log when regulation or transactional correctness requires one.

# %%
history_entries = lab_memory.history(memory_id)
show_rows(
    "Memory history",
    history_entries,
    ["event", "old_memory", "new_memory", "created_at", "is_deleted"],
)

# %% [markdown]
### 5. Prove entity isolation

Mem0 supports four identity dimensions:

| Dimension | Typical meaning | Example |
|---|---|---|
| `user_id` | durable person/account context | `customer-1042` |
| `agent_id` | memory belonging to one agent persona | `travel-assistant` |
| `app_id` | application or deployment boundary | `mobile-app` |
| `run_id` | temporary session, ticket, or experiment | `ticket-9081` |

Writes may use these identifiers; reads must use trusted filters. Never accept authorization scope directly from an untrusted browser and assume memory filtering alone is access control.

# %%
other_user_results = lab_memory.get_all(filters={"user_id": LAB_OTHER_USER})
scope_isolated = rows_from(other_user_results) == []

show_json(
    "The other user cannot retrieve primer-user's memory",
    {
        "requested_user": LAB_OTHER_USER,
        "result_count": len(rows_from(other_user_results)),
        "isolated": scope_isolated,
    },
)

# %% [markdown]
### 6. Delete and verify

Deletion should be a first-class product capability: users need a way to correct or forget stored context. Bulk deletion is intentionally not demonstrated automatically because its scope can be destructive.

# %%
delete_response = lab_memory.delete(memory_id)
remaining_rows = rows_from(lab_memory.get_all(filters={"user_id": LAB_USER}))
deleted = remaining_rows == []

show_json("Delete response", delete_response)
show_json("Verification after delete", {"remaining": remaining_rows, "deleted": deleted})

print(
    "MEM0_OFFLINE_CRUD "
    "first_value=concise "
    f"updated_value={'detailed' if 'detailed' in record_after_update['memory'] else 'unexpected'} "
    f"history_entries={len(history_entries)} "
    f"deleted={deleted}"
)

# %% [markdown]
## Live extraction lab — optional

The default offline walkthrough proves real Mem0 storage and maintenance without asking an LLM to decide anything.

Choose `oss_openai`, `oss_ollama`, or `platform` to run the conversation below through a real extraction model. The example contains response style, measurement units, a dietary preference, and conversational filler that should not become memory. Extraction quality is visible, not assumed.

# %%
LIVE_USER = f"primer-live-user-{uuid4().hex[:10]}"
LIVE_METADATA = {"source": "mem0_primer", "demo_run": LIVE_USER}
LIVE_CONVERSATION = [
    {
        "role": "user",
        "content": (
            "Please keep future answers concise and use metric units. "
            "I am vegetarian. Thanks for helping me today!"
        ),
    },
    {
        "role": "assistant",
        "content": "Understood. I will tailor future responses to those preferences.",
    },
]

live_backend: Memory | MemoryClient | None = None
live_add_response: dict[str, Any] | None = None
live_rows: list[dict[str, Any]] = []

if MODE in {"oss_openai", "oss_ollama"}:
    live_backend = build_in_memory_oss(MODE)
    live_add_response = live_backend.add(
        LIVE_CONVERSATION,
        user_id=LIVE_USER,
        metadata=LIVE_METADATA,
        infer=True,
    )
    live_rows = rows_from(live_backend.get_all(filters={"user_id": LIVE_USER}))
elif MODE == "platform":
    live_backend = MemoryClient(api_key=os.environ["MEM0_API_KEY"])
    live_add_response = live_backend.add(
        LIVE_CONVERSATION,
        user_id=LIVE_USER,
        metadata=LIVE_METADATA,
        infer=True,
    )
    # Platform v3 extraction is asynchronous. Poll the public get_all operation
    # with a small bounded wait until this unique demo user has memories.
    for _ in range(20):
        live_rows = rows_from(
            live_backend.get_all(
                filters={"user_id": LIVE_USER},
                page=1,
                page_size=100,
            )
        )
        if live_rows:
            break
        time.sleep(1)

if MODE == "offline":
    display(
        Markdown(
            "**Live extraction skipped.** Set `MEM0_PRIMER_MODE=oss_openai`, "
            "`oss_ollama`, or `platform`, restart the kernel, and run all cells."
        )
    )
else:
    show_json("Live add response", live_add_response)
    show_rows(
        "Memories selected by the extraction model",
        live_rows,
        ["id", "memory", "user_id", "categories", "created_at"],
    )

# %% [markdown]
### Search the inferred memories

Search is separate from extraction. A good application uses a natural-language query, trusted entity filters, a small `top_k`, and enough metadata to explain where the memory came from. Retrieval results are context for the next response—not unquestionable truth.

# %%
live_search_rows: list[dict[str, Any]] = []
if live_backend is not None and live_rows:
    live_search = live_backend.search(
        "How should I tailor recommendations and explanations for this user?",
        filters={"user_id": LIVE_USER},
        top_k=5,
    )
    live_search_rows = rows_from(live_search)
    show_rows(
        "Live semantic search",
        live_search_rows,
        ["id", "memory", "score", "categories", "user_id"],
    )
else:
    display(Markdown("*No live search was run in offline mode.*"))

# %% [markdown]
## Where memory enters an AI application

1. Receive the user request.
2. Search memory using a trusted identity scope.
3. Place only relevant memories in the model context.
4. Retrieve authoritative documents separately when RAG is needed.
5. Let the model answer.
6. After the turn, decide whether anything new deserves long-term memory.
7. Store with `infer=True`, `infer=False`, or not at all.

Do not pass every memory into every prompt. Retrieval keeps personalization focused and token usage bounded.

# %%
def memory_context_for_prompt(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "No relevant long-term memories were retrieved."
    lines = [f"- {row.get('memory', '')}" for row in memories[:5]]
    return "Relevant long-term memories:\n" + "\n".join(lines)


example_context = memory_context_for_prompt(live_search_rows or [record_after_update])
display(
    HTML(
        "<div style='border-left:5px solid #7c3aed;background:#f5f3ff;"
        "padding:16px;border-radius:8px'><b>Example context added before a model call</b>"
        f"<pre style='white-space:pre-wrap'>{html.escape(example_context)}</pre></div>"
    )
)

# %% [markdown]
## The “primary key” question

Mem0 gives each stored memory a unique **memory ID**. That ID is the natural handle for `get`, `update`, `history`, and `delete`.

Applications often think in business keys:

```text
(tenant_id, user_id, preference_type) → mem0_memory_id
```

For deterministic preferences:

1. Look up the business key in your database.
2. If no memory ID exists, call `add(..., infer=False)` and save the returned ID.
3. If an ID exists, call `update(memory_id, ...)`.
4. Update text and metadata together.
5. On erasure, call `delete(memory_id)` and remove the mapping.

For conversational extraction with `infer=True`, do not assume extraction behaves like a relational upsert. Treat inferred memories as extracted context; use explicit IDs when deterministic replacement is required.

# %% [markdown]
## Capability map

| Capability | What it provides | Main design question |
|---|---|---|
| Automatic extraction | LLM selects useful memories | What should be extracted or excluded? |
| Direct storage | Exact text with `infer=False` | Who validates the value? |
| Semantic search | Relevant memories for a new question | Which trusted filters and threshold? |
| Entity scoping | User, agent, app, and run partitions | Which scopes are long-lived? |
| Metadata filters | Application-specific partitioning | Which fields are safe and stable? |
| Update and history | Correction with an inspectable trail | Which business key maps to the memory ID? |
| Delete and lifecycle | Erasure and retention | Who may delete, and how is it verified? |
| Managed Platform | Hosted storage and dashboard | Data residency, cost, quotas, and availability? |
| OSS | Provider and storage control | Who operates models, vectors, and backups? |
| Entity linking | Connections across memories | Does the use case truly need relationships? |

# %% [markdown]
## Evaluation

A memory feature is not complete merely because `add` and `search` return data. Evaluate:

- **Extraction precision:** saved details were useful.
- **Extraction recall:** important details were not missed.
- **Retrieval hit rate:** the correct memory appears for representative questions.
- **Isolation:** one user, agent, app, or run cannot retrieve another scope.
- **Freshness:** corrected memories replace or supersede stale context.
- **Contradiction rate:** conflicting memories do not silently drive answers.
- **Deletion verification:** forgotten memories no longer appear.
- **Latency and cost:** extraction and retrieval remain affordable.
- **Answer lift:** memory improves the answer compared with a no-memory baseline.

# %%
evaluation_checks = [
    {
        "check": "Direct storage preserved the validated value",
        "passed": record_before_update["memory"] == "Preference answer_style: concise",
    },
    {
        "check": "Explicit update retained the same memory ID",
        "passed": same_id_after_update,
    },
    {
        "check": "History captured ADD and UPDATE",
        "passed": {row["event"] for row in history_entries} >= {"ADD", "UPDATE"},
    },
    {
        "check": "Different user scope returned no memory",
        "passed": scope_isolated,
    },
    {
        "check": "Delete removed the memory from the original scope",
        "passed": deleted,
    },
]
evaluation_pass_rate = sum(item["passed"] for item in evaluation_checks) / len(
    evaluation_checks
)
show_rows("Deterministic notebook checks", evaluation_checks, ["check", "passed"])
print(f"EVALUATION_PASS_RATE {evaluation_pass_rate:.2f}")

# %% [markdown]
## Privacy and governance

| Store with care | Keep somewhere else |
|---|---|
| User-approved preferences | Passwords, API keys, authentication tokens |
| Stable personalization details | Authoritative balances or permissions |
| Goals and recurring constraints | Full private documents copied without need |
| Summaries of useful outcomes | Hidden reasoning or tool scratchpads |
| Consent and provenance metadata | Sensitive PII without a lawful purpose |
| Retention/expiration metadata | Anything you cannot reliably delete |

Practical controls:

1. Obtain consent and make remembered items visible.
2. Scope reads and writes with trusted server-side identity.
3. Redact secrets before calling Mem0.
4. Define retention, correction, export, and erasure.
5. Keep authoritative data in its system of record.
6. Log memory use without logging secret content.
7. Test isolation and deletion continuously.

**Privacy is an application responsibility even when storage is managed.**

# %% [markdown]
## Platform versus OSS decision guide

Choose **Mem0 Platform** for a managed service, dashboard, shared persistence, and reduced operational work.

Choose **Mem0 OSS** for provider choice, storage control, local experimentation, or self-hosting.

Choose **in-memory OSS** for notebooks and disposable experiments. Restarting the kernel removes the vector store and history.

A practical adoption path:

1. Prototype in memory.
2. Build a small gold evaluation set.
3. Decide which data is inferred versus application-owned.
4. Validate Privacy, identity, update, and deletion.
5. Compare Platform and self-hosted cost/operations.
6. Persist only after the memory policy is stable.

# %% [markdown]
## Optional live cleanup

Platform mode creates a unique demo user. By default, this notebook deletes the memories it created after displaying them. Set `MEM0_PRIMER_CLEANUP=0` before execution if you intentionally want to inspect them later in the Mem0 dashboard.

The notebook never performs an unfiltered or wildcard delete.

# %%
cleanup_requested = os.getenv("MEM0_PRIMER_CLEANUP", "1") == "1"
cleanup_count = 0

if MODE == "platform" and cleanup_requested and live_backend is not None:
    for row in live_rows:
        row_id = row.get("id")
        if isinstance(row_id, str):
            live_backend.delete(row_id)
            cleanup_count += 1
    print(f"platform_cleanup deleted_memories={cleanup_count} user_id={LIVE_USER}")
elif MODE == "platform":
    print(f"platform_cleanup skipped user_id={LIVE_USER}")
else:
    print("platform_cleanup not_applicable")

# %% [markdown]
## Version and API notes

This notebook was written against the installed `mem0ai` 2.x API and prints the exact version at runtime. Mem0's managed API and extraction algorithms can evolve, so confirm behavior before copying a call into another project.

Current official references:

- [Mem0 introduction](https://docs.mem0.ai/introduction)
- [OSS Python quickstart](https://docs.mem0.ai/open-source/python-quickstart)
- [Add memories and `infer`](https://docs.mem0.ai/api-reference/memory/add-memories)
- [Search memories](https://docs.mem0.ai/core-concepts/memory-operations/search)
- [Entity-scoped memory](https://docs.mem0.ai/platform/features/entity-scoped-memory)
- [Update memory](https://docs.mem0.ai/core-concepts/memory-operations/update)
- [Delete memory](https://docs.mem0.ai/core-concepts/memory-operations/delete)
- [Memory evaluation](https://docs.mem0.ai/core-concepts/memory-evaluation)

When documentation and an installed SDK disagree, inspect installed method signatures and run a disposable contract test before adopting the behavior.

# %%
assert evaluation_pass_rate == 1.0
assert deleted is True
assert scope_isolated is True
assert same_id_after_update is True

selected_backend = {
    "offline": "mem0_oss_qdrant_ram",
    "oss_openai": "mem0_oss_qdrant_ram_openai",
    "oss_ollama": "mem0_oss_qdrant_ram_ollama",
    "platform": "mem0_platform",
}[MODE]

print(
    f"MEM0_PRIMER_OK mode={MODE} "
    f"selected_backend={selected_backend} "
    "secrets_printed=False"
)
"""


def build_notebook() -> nbformat.NotebookNode:
    cells: list[nbformat.NotebookNode] = []
    kind: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if kind is None:
            return
        source = "\n".join(buffer).strip()
        if kind == "markdown":
            cells.append(nbformat.v4.new_markdown_cell(source))
        else:
            cells.append(nbformat.v4.new_code_cell(source))

    for line in SOURCE.splitlines():
        if line == "# %% [markdown]":
            flush()
            kind = "markdown"
            buffer = []
        elif line == "# %%":
            flush()
            kind = "code"
            buffer = []
        else:
            buffer.append(line)
    flush()

    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata.update(
        {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "mem0_primer": True,
            "domain_neutral": True,
        }
    )
    return notebook


if __name__ == "__main__":
    nbformat.write(build_notebook(), TARGET)
    print(f"Wrote {TARGET.relative_to(ROOT)}")
