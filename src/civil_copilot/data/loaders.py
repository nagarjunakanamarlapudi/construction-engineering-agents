"""Load the portable corpus used by stores, tests, notebooks, and local fallbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from civil_copilot.data.models import Corpus, DocumentChunk, GoldScenario, ProjectRecord, Relationship


ModelType = TypeVar("ModelType", bound=BaseModel)


def _read_jsonl(path: Path, model: type[ModelType]) -> list[ModelType]:
    if not path.exists():
        return []
    return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _load_public_bis(path: Path) -> tuple[list[ProjectRecord], list[DocumentChunk]]:
    if not path.exists():
        return [], []
    raw_chunks: list[dict[str, Any]] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    by_source: dict[str, dict[str, Any]] = {}
    for chunk in raw_chunks:
        by_source.setdefault(chunk["source_id"], chunk)

    records = [
        ProjectRecord(
            record_id=f"PUBLIC-BIS-{source_id}",
            project_id="PUBLIC-REFERENCE",
            record_type="public_standard_preview",
            title=f"{item.get('designation', source_id)} — {item.get('title', 'BIS public preview')}",
            content=(
                "Official public BIS preview or catalogue material. This is not represented as the "
                "complete Indian Standard."
            ),
            status=item.get("status", "unknown"),
            revision=item.get("designation", "catalogue"),
            effective_date="2026-08-23",
            data_origin="public_official",
            source_path=f"data/public/bis/academic/INDEX.jsonl#{source_id}",
            source_url=item.get("source_url"),
            access_scopes=["public"],
            metadata={key: value for key, value in item.items() if key not in {"text"}},
        )
        for source_id, item in sorted(by_source.items())
    ]
    chunks = [
        DocumentChunk(
            chunk_id=item["chunk_id"],
            record_id=f"PUBLIC-BIS-{item['source_id']}",
            project_id="PUBLIC-REFERENCE",
            text=item["text"],
            ordinal=max(int(item["chunk_id"].rsplit("-", 1)[-1]) - 1, 0),
            data_origin="public_official",
            source_path=f"data/public/bis/academic/INDEX.jsonl#{item['chunk_id']}",
            source_url=item.get("source_url"),
            access_scopes=["public"],
            metadata={key: value for key, value in item.items() if key not in {"text"}},
        )
        for item in raw_chunks
    ]
    return records, chunks


def load_corpus(root: Path | str = Path.cwd()) -> Corpus:
    """Load generated synthetic files plus official public BIS preview chunks."""

    root = Path(root)
    synthetic = root / "data" / "synthetic" / "steel_building_demo"
    records = _read_jsonl(synthetic / "records.jsonl", ProjectRecord)
    chunks = _read_jsonl(synthetic / "chunks.jsonl", DocumentChunk)
    relationships = _read_jsonl(synthetic / "relationships.jsonl", Relationship)
    public_records, public_chunks = _load_public_bis(
        root / "data" / "public" / "bis" / "academic" / "INDEX.jsonl"
    )
    return Corpus(
        records=[*records, *public_records],
        chunks=[*chunks, *public_chunks],
        relationships=relationships,
    )


def load_gold_scenarios(path: Path | str) -> list[GoldScenario]:
    """Load the versioned evaluation and UI demonstration scenarios."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GoldScenario.model_validate(item) for item in raw]
