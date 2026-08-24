#!/usr/bin/env python3
"""Ingest, re-index, validate, and report local project data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from civil_copilot.config import Settings
from civil_copilot.data.loaders import load_corpus
from civil_copilot.ingestion.service import IngestionService
from civil_copilot.stores.neo4j import Neo4jGraphStore
from civil_copilot.stores.postgres import PostgresRecordStore
from civil_copilot.stores.qdrant import (
    LIVE_QDRANT_COLLECTION,
    OpenAIEmbedding,
    QdrantSearchStore,
)

ROOT = Path(__file__).resolve().parents[1]


def _stores(settings: Settings) -> tuple[PostgresRecordStore, QdrantSearchStore, Neo4jGraphStore]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to build the production semantic index")
    embedding = OpenAIEmbedding(
        settings.openai_api_key.get_secret_value(), settings.openai_embedding_model
    )
    records = PostgresRecordStore(str(settings.database_url))
    search = QdrantSearchStore(
        str(settings.qdrant_url),
        embedding,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        collection_name=LIVE_QDRANT_COLLECTION,
    )
    graph = Neo4jGraphStore(
        settings.neo4j_uri,
        settings.neo4j_username,
        settings.neo4j_password.get_secret_value(),
    )
    return records, search, graph


def _file_counts() -> dict[str, int]:
    corpus = load_corpus(ROOT)
    return {
        "records": len(corpus.records),
        "chunks": len(corpus.chunks),
        "relationships": len(corpus.relationships),
        "public_records": sum(record.data_origin == "public_official" for record in corpus.records),
        "synthetic_records": sum(
            record.data_origin == "synthetic_academic_demo" for record in corpus.records
        ),
    }


def _report(report: Any) -> dict[str, Any]:
    return {
        name: {
            "created": getattr(report, name).created,
            "updated": getattr(report, name).updated,
            "unchanged": getattr(report, name).unchanged,
            "total": getattr(report, name).total,
        }
        for name in ("records", "chunks", "graph_nodes", "relationships")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reindex", choices=["all", "documents", "graph"])
    parser.add_argument("--reset-indexes", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()

    if args.status:
        print(json.dumps({"source_files": _file_counts()}, indent=2, sort_keys=True))
        return 0

    settings = Settings()
    records, search, graph = _stores(settings)
    try:
        if args.reset_indexes:
            if args.confirm != "reset-local-indexes":
                raise RuntimeError("--reset-indexes requires --confirm reset-local-indexes")
            search.clear()
            graph.clear()
            print(json.dumps({"reset": ["qdrant", "neo4j"]}, sort_keys=True))
            return 0

        if args.reindex in {"all", "documents"}:
            search.clear()
        if args.reindex in {"all", "graph"}:
            graph.clear()

        corpus = load_corpus(ROOT)
        report = IngestionService(records, search, graph).ingest(
            corpus.records, corpus.chunks, corpus.relationships
        )
        print(json.dumps({"ingestion": _report(report)}, indent=2, sort_keys=True))
        return 0
    finally:
        graph.close()


if __name__ == "__main__":
    raise SystemExit(main())
