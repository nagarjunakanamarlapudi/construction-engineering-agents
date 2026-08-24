"""Deterministic, connected academic data for one Indian structural-steel project."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from civil_copilot.data.models import (
    Corpus,
    DocumentChunk,
    GoldScenario,
    ProjectRecord,
    Relationship,
)

PROJECT_ID = "BLR-STEEL-DEMO"
SOURCE_PATH = "data/synthetic/steel_building_demo/records.jsonl"
LABEL = "SYNTHETIC — ACADEMIC DEMO"
START_DATE = date(2026, 1, 5)


def _jsonl(records: Iterable[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records
    )


def _record(
    record_id: str,
    record_type: str,
    title: str,
    content: str,
    *,
    revision: str = "1",
    day: int = 0,
    status: str = "current",
    metadata: dict[str, Any] | None = None,
) -> ProjectRecord:
    return ProjectRecord(
        record_id=record_id,
        project_id=PROJECT_ID,
        record_type=record_type,
        title=f"{LABEL}: {title}",
        content=f"{LABEL}. {content}",
        status=status,
        revision=revision,
        effective_date=START_DATE + timedelta(days=day),
        data_origin="synthetic_academic_demo",
        source_path=f"{SOURCE_PATH}#{record_id}",
        access_scopes=["project:blr-steel-demo"],
        metadata={"synthetic": True, "academic_use": True, **(metadata or {})},
    )


def _chunk(record: ProjectRecord) -> DocumentChunk:
    text = (
        f"{record.title}. Record {record.record_id}; type {record.record_type}; status "
        f"{record.status}; revision {record.revision}; effective {record.effective_date}. "
        f"{record.content}"
    )
    return DocumentChunk(
        chunk_id=f"{record.record_id}-chunk-0001",
        record_id=record.record_id,
        project_id=record.project_id,
        text=text,
        ordinal=0,
        data_origin=record.data_origin,
        source_path=record.source_path,
        access_scopes=record.access_scopes,
        metadata={
            "record_type": record.record_type,
            "revision": record.revision,
            "status": record.status,
            **record.metadata,
        },
    )


def generate_demo_project(seed: int = 800) -> Corpus:
    """Build a reproducible, internally connected project; no random facts are inferred."""

    records: list[ProjectRecord] = []
    links: list[Relationship] = []
    link_number = 0

    def add(record: ProjectRecord) -> None:
        records.append(record)

    def connect(source: str, relation: str, target: str, day: int = 0, note: str = "") -> None:
        nonlocal link_number
        link_number += 1
        links.append(
            Relationship(
                relationship_id=f"REL-{link_number:04d}",
                project_id=PROJECT_ID,
                source_id=source,
                target_id=target,
                relationship_type=relation,
                provenance=f"Synthetic scenario rule {seed}: {note or relation}",
                method="synthetic_ground_truth",
                confidence=1.0,
                valid_from=START_DATE + timedelta(days=day),
                metadata={"synthetic": True, "seed": seed},
            )
        )

    add(
        _record(
            "PROJECT-BLR-01",
            "project",
            "Bengaluru Logistics Steel Building",
            "A four-level logistics and office building used only to demonstrate connected project questions.",
            metadata={"location": "Bengaluru, Karnataka", "seed": seed},
        )
    )
    add(
        _record(
            "CODE-REGISTER-001",
            "code_register",
            "Approved Indian standards register",
            "The design basis adopts listed Indian Standards by exact edition; public BIS material is a preview, not the full standard.",
            revision="2",
            day=2,
        )
    )
    connect("PROJECT-BLR-01", "HAS_REGISTER", "CODE-REGISTER-001", day=2)

    codes = [
        ("CODE-IS-800", "IS 800:2007", "General construction in steel", "structural design"),
        ("CODE-IS-2062", "IS 2062:2011", "Hot rolled structural steel", "material grade"),
        ("CODE-IS-875-1", "IS 875 Part 1:1987", "Dead loads", "dead load"),
        ("CODE-IS-875-2", "IS 875 Part 2:1987", "Imposed loads", "live load"),
        ("CODE-IS-875-3", "IS 875 Part 3:2015", "Wind loads", "wind load"),
        (
            "CODE-IS-1893-1",
            "IS 1893 Part 1:2016",
            "Earthquake-resistant design criteria",
            "seismic load",
        ),
        ("CODE-IS-816", "IS 816:1969", "Metal arc welding for mild steel", "welding"),
        ("CODE-IS-9595", "IS 9595:1996", "Metal arc welding recommendations", "welding quality"),
    ]
    for record_id, designation, title, use in codes:
        add(
            _record(
                record_id,
                "code_reference",
                designation,
                f"Project code-register entry for {title}; used for {use}. Refer to the licensed project copy for compliance decisions.",
                revision="approved-edition",
                day=2,
                metadata={"designation": designation, "content_scope": "project_register_entry"},
            )
        )
        connect("CODE-REGISTER-001", "ADOPTS", record_id, day=2, note=designation)

    for number in range(1, 13):
        spec_id = f"SPEC-STEEL-{number:02d}"
        code_id = codes[(number - 1) % len(codes)][0]
        add(
            _record(
                spec_id,
                "specification",
                f"Structural steel specification section {number:02d}",
                f"Section {number:02d} defines approved material, fabrication, erection, inspection, and acceptance requirements. Governing register entry: {code_id}.",
                revision="A",
                day=4,
                metadata={"section": f"05 12 {number:02d}", "governing_code_id": code_id},
            )
        )
        connect(spec_id, "IMPLEMENTS", code_id, day=4)

    for number in range(1, 13):
        calc_id = f"CALC-FRAME-{number:02d}"
        spec_id = f"SPEC-STEEL-{number:02d}"
        add(
            _record(
                calc_id,
                "calculation",
                f"Frame and connection calculation package {number:02d}",
                f"Checked design calculation for grid line {number}; based on {spec_id} and the approved load criteria.",
                revision="C",
                day=10 + number,
                status="approved",
                metadata={"designer": "Demo Structural Consultants", "grid": str(number)},
            )
        )
        connect(calc_id, "DERIVED_FROM", spec_id, day=10 + number)

    for number in range(1, 13):
        drawing_number = 200 + number
        older_id = f"DRAW-S-{drawing_number}-R3"
        current_id = f"DRAW-S-{drawing_number}-R5"
        calc_id = f"CALC-FRAME-{number:02d}"
        add(
            _record(
                older_id,
                "drawing",
                f"S-{drawing_number} framing plan revision 3",
                f"Superseded issued-for-construction framing plan for grid {number}. Use {current_id} for current work.",
                revision="3",
                day=25 + number,
                status="superseded",
                metadata={"document_number": f"S-{drawing_number}", "discipline": "structural"},
            )
        )
        add(
            _record(
                current_id,
                "drawing",
                f"S-{drawing_number} framing plan revision 5",
                f"Current issued-for-construction plan for grid {number}, incorporating reviewed design decisions and connection details.",
                revision="5",
                day=50 + number,
                status="current",
                metadata={"document_number": f"S-{drawing_number}", "discipline": "structural"},
            )
        )
        connect(current_id, "REVISES", older_id, day=50 + number)
        connect(calc_id, "SUPPORTS", current_id, day=50 + number)

    activity_ids: list[str] = []
    for number in range(1, 31):
        activity_id = f"ACT-STEEL-{number:03d}"
        activity_ids.append(activity_id)
        level = (number - 1) // 6 + 1
        add(
            _record(
                activity_id,
                "schedule_activity",
                f"Steel work activity {number:03d}",
                f"Fabricate, deliver, or erect structural steel for level {level}, zone {(number - 1) % 6 + 1}. Planned duration: {3 + number % 5} days.",
                revision="baseline-2",
                day=35 + number,
                status="planned" if number > 12 else "in_progress",
                metadata={
                    "level": level,
                    "zone": (number - 1) % 6 + 1,
                    "critical": number in {8, 9, 10, 11},
                    "total_float_days": 0 if number in {8, 9, 10, 11} else 2,
                },
            )
        )
        connect(activity_id, "DELIVERS", "PROJECT-BLR-01", day=35 + number)
        if number > 1:
            connect(activity_id, "DEPENDS_ON", activity_ids[-2], day=35 + number)

    for number in range(81, 96):
        rfi_id = f"RFI-{number:03d}"
        drawing_number = 201 + (number - 81) % 12
        drawing_old = f"DRAW-S-{drawing_number}-R3"
        drawing_current = f"DRAW-S-{drawing_number}-R5"
        activity_id = activity_ids[(number - 81) * 2]
        if number == 87:
            drawing_old = "DRAW-S-204-R3"
            drawing_current = "DRAW-S-204-R5"
            activity_id = "ACT-STEEL-009"
            content = (
                "Site requested clarification of beam-to-column connection C17 shown on S-204 Rev 3. "
                "The approved response required plate PL-17B and was incorporated in S-204 Rev 5. "
                "Activity ACT-STEEL-009 remained blocked until the revised drawing was issued."
            )
            status = "closed"
        else:
            content = (
                f"Technical clarification references {drawing_old}; the response is incorporated in "
                f"{drawing_current} and is linked to {activity_id}."
            )
            status = "closed" if number < 91 else "open"
        add(
            _record(
                rfi_id,
                "rfi",
                f"Structural clarification {number:03d}",
                content,
                revision="response-1",
                day=60 + number - 81,
                status=status,
                metadata={"discipline": "structural", "responsible_party": "Structural Designer"},
            )
        )
        connect(rfi_id, "REFERENCES", drawing_old, day=60 + number - 81)
        connect(rfi_id, "CHANGES_OR_CLARIFIES", drawing_current, day=65 + number - 81)
        connect(rfi_id, "AFFECTS", activity_id, day=60 + number - 81)

    piece_ids: list[str] = []
    weld_ids: list[str] = []
    for po_number in range(1, 9):
        po_id = f"PO-STEEL-{po_number:03d}"
        add(
            _record(
                po_id,
                "purchase_order",
                f"Structural steel purchase order lot {po_number}",
                f"Purchase of IS 2062 structural steel for fabrication lot {po_number}, approved vendor and delivery window recorded.",
                revision="2",
                day=20 + po_number,
                status="released",
                metadata={"vendor": f"Demo Steel Vendor {po_number:02d}", "currency": "INR"},
            )
        )
        connect(po_id, "GOVERNED_BY", "SPEC-STEEL-01", day=20 + po_number)
        for certificate_index in range(1, 3):
            mtc_id = f"MTC-{po_number:02d}-{certificate_index:02d}"
            heat = f"HT-{seed}-{po_number:02d}{certificate_index:02d}"
            add(
                _record(
                    mtc_id,
                    "material_certificate",
                    f"Mill test certificate {heat}",
                    f"Synthetic mill certificate for heat {heat}; material grade E250 and measured properties are for demo retrieval only.",
                    revision="original",
                    day=72 + po_number,
                    status="accepted",
                    metadata={"heat_number": heat, "grade": "E250", "standard": "IS 2062"},
                )
            )
            connect(po_id, "FULFILLED_BY", mtc_id, day=72 + po_number)
            for local_piece in range(1, 4):
                piece_number = (po_number - 1) * 6 + (certificate_index - 1) * 3 + local_piece
                piece_id = f"PIECE-C{piece_number:03d}"
                piece_ids.append(piece_id)
                drawing_id = f"DRAW-S-{201 + (piece_number - 1) % 12}-R5"
                add(
                    _record(
                        piece_id,
                        "piece",
                        f"Fabricated column piece C{piece_number:03d}",
                        f"Column piece fabricated from heat {heat}, defined by {drawing_id}, and allocated to level {(piece_number - 1) // 10 + 1}.",
                        revision="fabricated",
                        day=90 + piece_number,
                        status="installed" if piece_number <= 30 else "fabricated",
                        metadata={"piece_mark": f"C{piece_number:03d}", "heat_number": heat},
                    )
                )
                connect(mtc_id, "USED_IN", piece_id, day=90 + piece_number)
                connect(piece_id, "DEFINED_BY", drawing_id, day=90 + piece_number)
                connect(
                    piece_id,
                    "INSTALLED_BY",
                    activity_ids[(piece_number - 1) % 30],
                    day=100 + piece_number,
                )

    ncr_inspection_numbers = (4, 8, 12, 16, 17, 18)
    open_ncr_inspection_numbers = {17, 18}
    for number in range(1, 25):
        weld_id = f"WELD-{number:03d}"
        weld_ids.append(weld_id)
        left_piece = piece_ids[(number - 1) * 2]
        right_piece = piece_ids[(number * 2 - 1) % len(piece_ids)]
        add(
            _record(
                weld_id,
                "weld",
                f"Site weld {number:03d}",
                f"Site weld joins {left_piece} and {right_piece}; WPS-01 and qualified welder DEMO-W{number % 6 + 1} recorded.",
                revision="weld-log-1",
                day=135 + number,
                status=(
                    "repair_required"
                    if number in open_ncr_inspection_numbers
                    else "accepted"
                    if number <= 18
                    else "awaiting_inspection"
                ),
                metadata={"wps": "WPS-01", "welder": f"DEMO-W{number % 6 + 1}"},
            )
        )
        connect(weld_id, "JOINS", left_piece, day=135 + number)
        connect(weld_id, "JOINS", right_piece, day=135 + number)
        connect(weld_id, "GOVERNED_BY", "CODE-IS-816", day=135 + number)

    inspection_ids: list[str] = []
    for number in range(1, 19):
        inspection_id = f"INSP-WELD-{number:03d}"
        inspection_ids.append(inspection_id)
        result = "rejected" if number in ncr_inspection_numbers else "accepted"
        add(
            _record(
                inspection_id,
                "inspection",
                f"Weld inspection {number:03d}",
                f"Visual and NDT review of WELD-{number:03d}; recorded result: {result}.",
                revision="report-1",
                day=165 + number,
                status=result,
                metadata={"result": result, "inspection_type": "visual_and_ut"},
            )
        )
        connect(inspection_id, "TESTS", f"WELD-{number:03d}", day=165 + number)

    for number, inspection_number in enumerate(ncr_inspection_numbers, start=1):
        ncr_id = f"NCR-{number:03d}"
        inspection_id = f"INSP-WELD-{inspection_number:03d}"
        closure_id = f"INSP-RECHECK-{number:03d}"
        add(
            _record(
                ncr_id,
                "ncr",
                f"Weld non-conformance {number:03d}",
                f"Raised from {inspection_id}; repair by approved procedure and repeat inspection {closure_id} required.",
                revision="closure-1",
                day=190 + number,
                status="closed" if number <= 4 else "open",
                metadata={"disposition": "repair_and_reinspect"},
            )
        )
        add(
            _record(
                closure_id,
                "inspection",
                f"NCR reinspection {number:03d}",
                f"Repeat inspection after repair of {ncr_id}; {'accepted' if number <= 4 else 'scheduled'}.",
                revision="report-1",
                day=200 + number,
                status="accepted" if number <= 4 else "scheduled",
                metadata={"result": "accepted" if number <= 4 else "pending"},
            )
        )
        connect(inspection_id, "RAISES", ncr_id, day=190 + number)
        connect(ncr_id, "CORRECTED_BY", closure_id, day=200 + number)
        connect(ncr_id, "AFFECTS", activity_ids[(inspection_number - 1) % 30], day=190 + number)

    for number in range(1, 9):
        minute_id = f"MIN-STEEL-{number:02d}"
        rfi_id = f"RFI-{80 + number:03d}"
        add(
            _record(
                minute_id,
                "meeting_minute",
                f"Weekly steel coordination meeting {number}",
                f"The team reviewed {rfi_id}, its responsible party, due date, linked drawing, and affected activity.",
                revision="issued",
                day=75 + number * 7,
                status="issued",
                metadata={"meeting_number": number},
            )
        )
        connect(minute_id, "DISCUSSES", rfi_id, day=75 + number * 7)

    for number in range(1, 9):
        handover_id = f"HANDOVER-STEEL-{number:02d}"
        piece_id = piece_ids[number - 1]
        add(
            _record(
                handover_id,
                "handover",
                f"Steel handover package {number}",
                f"As-built, inspection, punch closure, and material traceability package for {piece_id}.",
                revision="A",
                day=230 + number,
                status="accepted" if number <= 4 else "draft",
                metadata={"package": f"STEEL-HO-{number:02d}"},
            )
        )
        connect(handover_id, "HANDOVER_EVIDENCE_FOR", piece_id, day=230 + number)

    chunks = [_chunk(record) for record in records]
    return Corpus(records=records, chunks=chunks, relationships=links)


def write_demo_project(corpus: Corpus, output_dir: Path) -> dict[str, Any]:
    """Publish sorted JSONL files and a checksum manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    records = [
        record.model_dump(mode="json")
        for record in sorted(corpus.records, key=lambda item: item.record_id)
    ]
    chunks = [
        chunk.model_dump(mode="json")
        for chunk in sorted(corpus.chunks, key=lambda item: item.chunk_id)
    ]
    relationships = [
        link.model_dump(mode="json")
        for link in sorted(corpus.relationships, key=lambda item: item.relationship_id)
    ]
    payloads = {
        "records.jsonl": _jsonl(records),
        "chunks.jsonl": _jsonl(chunks),
        "relationships.jsonl": _jsonl(relationships),
    }
    for filename, text in payloads.items():
        (output_dir / filename).write_text(text, encoding="utf-8")

    record_ids = {record["record_id"] for record in records}
    dangling_count = sum(
        1
        for link in relationships
        if link["source_id"] not in record_ids or link["target_id"] not in record_ids
    )
    manifest = {
        "dataset_id": "SYNTH-BLR-STEEL-DEMO",
        "label": LABEL,
        "project_id": PROJECT_ID,
        "seed": 800,
        "record_count": len(records),
        "chunk_count": len(chunks),
        "relationship_count": len(relationships),
        "dangling_relationship_count": dangling_count,
        "files": {
            filename: hashlib.sha256(text.encode()).hexdigest()
            for filename, text in payloads.items()
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def default_gold_scenarios() -> list[GoldScenario]:
    """Questions selected to expose the difference between direct, graph, and agentic RAG."""

    return [
        GoldScenario(
            scenario_id="S-01",
            title="Exact record lookup",
            question="What did RFI-087 decide, and which drawing revision contains the decision?",
            expected_route="rag",
            expected_evidence_ids=["RFI-087"],
            expected_tools=["search_documents"],
            explanation="One targeted retrieval answers this exact-ID question.",
        ),
        GoldScenario(
            scenario_id="S-02",
            title="Indian standard scope",
            question="Which project code entries govern structural steel design and material grade?",
            expected_route="rag",
            expected_evidence_ids=["CODE-REGISTER-001", "CODE-IS-800", "CODE-IS-2062"],
            expected_tools=["search_documents"],
            explanation="The answer must distinguish the synthetic code register from public BIS previews.",
        ),
        GoldScenario(
            scenario_id="S-03",
            title="Downstream impact",
            question="What is downstream of RFI-087 if its decision is not implemented?",
            expected_route="graph_rag",
            expected_evidence_ids=["RFI-087", "DRAW-S-204-R5", "ACT-STEEL-009"],
            expected_tools=["find_graph_paths", "get_records"],
            explanation="The project graph follows the RFI-to-drawing-to-activity path.",
        ),
        GoldScenario(
            scenario_id="S-04",
            title="Delay investigation",
            question="Why was activity ACT-STEEL-009 blocked, what changed, and what evidence closes the issue?",
            expected_route="agentic_rag",
            expected_evidence_ids=["ACT-STEEL-009", "RFI-087", "DRAW-S-204-R3", "DRAW-S-204-R5"],
            expected_tools=["get_schedule_activity", "find_graph_paths", "compare_revisions"],
            explanation="The agent decomposes schedule, relationship, and revision checks.",
        ),
        GoldScenario(
            scenario_id="S-05",
            title="Material traceability",
            question="Trace PIECE-C001 from purchase order and mill certificate to installation and handover.",
            expected_route="graph_rag",
            expected_evidence_ids=["PIECE-C001", "MTC-01-01", "PO-STEEL-001", "HANDOVER-STEEL-01"],
            expected_tools=["find_graph_paths", "get_records"],
            explanation="Graph traversal assembles the material-to-piece evidence chain.",
        ),
        GoldScenario(
            scenario_id="S-06",
            title="Quality closure investigation",
            question="Which weld inspections raised NCRs, and which remain open pending reinspection?",
            expected_route="agentic_rag",
            expected_evidence_ids=["NCR-005", "NCR-006"],
            expected_tools=["query_quality_records", "find_graph_paths", "get_records"],
            explanation="The agent combines status filtering with inspection-to-NCR paths.",
        ),
        GoldScenario(
            scenario_id="S-07",
            title="IS 800 project evidence review",
            question=(
                "Compare this project's structural-steel practices with the indexed IS 800 "
                "preview. What is evidenced, not evidenced, and needs review?"
            ),
            expected_route="agentic_rag",
            expected_evidence_ids=[
                "CODE-IS-800",
                "PUBLIC-BIS-bis-800",
                "SPEC-STEEL-01",
                "MTC-01-01",
                "WELD-001",
            ],
            expected_tools=["assess_standard_evidence"],
            explanation=(
                "One bounded standards tool compares only indexed public-preview topics with "
                "permitted project evidence and states the preview limitation."
            ),
        ),
    ]
