"""Load the portable corpus used by stores, tests, notebooks, and local fallbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from civil_copilot.data.models import (
    Corpus,
    DocumentChunk,
    GoldScenario,
    ProjectRecord,
    Relationship,
)

# This table is deliberately exact and edition-specific. A missing edition remains
# unlinked rather than being guessed from a similar BIS catalogue entry.
EXACT_PROJECT_STANDARD_MAPPINGS: dict[str, str] = {
    "CODE-IS-1893-1": "PUBLIC-BIS-bis-1893-1-2016-amd2-reff2021",
    "CODE-IS-2062": "PUBLIC-BIS-bis-2062-2011-reff2021",
    "CODE-IS-800": "PUBLIC-BIS-bis-800",
    "CODE-IS-816": "PUBLIC-BIS-bis-816",
    "CODE-IS-875-2": "PUBLIC-BIS-bis-875-2-1987-reaff2023",
    "CODE-IS-875-3": "PUBLIC-BIS-bis-875-3-2015-amd2-reff2020",
    "CODE-IS-9595": "PUBLIC-BIS-bis-9595",
}


def _read_jsonl[ModelType: BaseModel](path: Path, model: type[ModelType]) -> list[ModelType]:
    if not path.exists():
        return []
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


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
            title=(
                f"{item.get('designation', source_id)} — {item.get('title', 'BIS public preview')}"
            ),
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


def _exact_standard_relationships(records: list[ProjectRecord]) -> list[Relationship]:
    records_by_id = {record.record_id: record for record in records}
    links: list[Relationship] = []
    for project_record_id, public_record_id in EXACT_PROJECT_STANDARD_MAPPINGS.items():
        project_record = records_by_id.get(project_record_id)
        public_record = records_by_id.get(public_record_id)
        if project_record is None or public_record is None:
            continue
        links.append(
            Relationship(
                relationship_id=f"REL-STANDARD-{project_record_id}",
                project_id=project_record.project_id,
                source_id=project_record_id,
                target_id=public_record_id,
                relationship_type="REFERENCES",
                provenance=(
                    "Explicit exact-edition mapping between the synthetic project code register "
                    "and the official BIS public preview catalogue record."
                ),
                method="explicit_standard_designation_mapping",
                confidence=1.0,
                valid_from=project_record.effective_date,
                metadata={
                    "project_source_classification": "synthetic_project_reference",
                    "public_source_classification": "public_official_preview",
                    "content_scope": "public_preview_or_metadata_not_full_standard",
                    "mapping_basis": "exact_designation_and_edition",
                },
            )
        )
    return links


def load_corpus(root: Path | str | None = None) -> Corpus:
    """Load generated synthetic files plus official public BIS preview chunks."""

    root = Path.cwd() if root is None else Path(root)
    synthetic = root / "data" / "synthetic" / "steel_building_demo"
    records = _read_jsonl(synthetic / "records.jsonl", ProjectRecord)
    chunks = _read_jsonl(synthetic / "chunks.jsonl", DocumentChunk)
    relationships = _read_jsonl(synthetic / "relationships.jsonl", Relationship)
    public_records, public_chunks = _load_public_bis(
        root / "data" / "public" / "bis" / "academic" / "INDEX.jsonl"
    )
    all_records = [*records, *public_records]
    return Corpus(
        records=all_records,
        chunks=[*chunks, *public_chunks],
        relationships=[*relationships, *_exact_standard_relationships(all_records)],
    )


def load_gold_scenarios(path: Path | str) -> list[GoldScenario]:
    """Load the versioned evaluation and UI demonstration scenarios."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GoldScenario.model_validate(item) for item in raw]
