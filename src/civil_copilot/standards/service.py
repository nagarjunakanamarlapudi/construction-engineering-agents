"""Deterministic, provenance-backed project evidence review for indexed BIS previews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from civil_copilot.data.models import ProjectRecord
from civil_copilot.retrieval.answer import AnswerResult, Citation

if TYPE_CHECKING:
    from civil_copilot.agents.tools import ProjectTools

EvidenceStatus = Literal["Evidenced", "Not evidenced", "Needs review", "Not applicable"]

PREVIEW_LIMITATION = (
    "This review compares project records only with the indexed official BIS public preview. "
    "The preview is not the full Indian Standard and cannot prove full compliance. Missing "
    "evidence is not proof that a practice was not followed; it identifies information for a "
    "qualified engineer to review."
)


class StandardEvidenceRow(BaseModel):
    topic_id: str
    topic: str
    status: EvidenceStatus
    reason: str
    project_evidence: list[Citation] = Field(min_length=1)
    official_source: Citation
    limitation: str = PREVIEW_LIMITATION


class StandardEvidenceReport(BaseModel):
    project_id: str
    standard: str
    standard_record_id: str
    official_record_id: str
    rows: list[StandardEvidenceRow] = Field(min_length=1)
    limitation: str = PREVIEW_LIMITATION

    @property
    def source_ids(self) -> list[str]:
        return list(
            dict.fromkeys(
                [self.standard_record_id, self.official_record_id]
                + [citation.record_id for row in self.rows for citation in row.project_evidence]
            )
        )


@dataclass(frozen=True)
class _TopicProfile:
    topic_id: str
    topic: str
    status: EvidenceStatus
    reason: str
    project_record_ids: tuple[str, ...]
    official_chunk_id: str


@dataclass(frozen=True)
class _StandardProfile:
    aliases: tuple[str, ...]
    designation: str
    project_record_id: str
    official_record_id: str
    topics: tuple[_TopicProfile, ...]


IS_800_PROFILE = _StandardProfile(
    aliases=("IS 800", "IS 800:2007", "IS 800 : 2007", "CODE-IS-800"),
    designation="IS 800:2007",
    project_record_id="CODE-IS-800",
    official_record_id="PUBLIC-BIS-bis-800",
    topics=(
        _TopicProfile(
            "steel-construction-scope",
            "The project identifies general hot-rolled structural-steel construction as its scope.",
            "Evidenced",
            "The project code entry and steel specifications identify IS 800 and "
            "structural-steel work.",
            ("CODE-IS-800", "SPEC-STEEL-01", "SPEC-STEEL-09"),
            "bis-800-chunk-0001",
        ),
        _TopicProfile(
            "material-references",
            "Structural-steel material is identified and traceable to an Indian material standard.",
            "Evidenced",
            "The project register references IS 2062 and a mill certificate records the grade "
            "and heat number.",
            ("CODE-IS-2062", "MTC-01-01"),
            "bis-800-chunk-0008",
        ),
        _TopicProfile(
            "welding-records",
            "Welding work records a procedure, qualified welder, and inspection result.",
            "Evidenced",
            "The project references an Indian welding practice and records a WPS, welder, "
            "and inspection.",
            ("CODE-IS-816", "WELD-001", "INSP-WELD-001"),
            "bis-800-chunk-0002",
        ),
        _TopicProfile(
            "fabrication-and-erection",
            "Fabrication and erection work is covered by specifications and scheduled activities.",
            "Evidenced",
            "A steel specification covers fabrication and erection, and the schedule records "
            "that work.",
            ("SPEC-STEEL-01", "ACT-STEEL-001"),
            "bis-800-chunk-0001",
        ),
        _TopicProfile(
            "inspection-and-acceptance",
            "Inspection and acceptance records are complete for the reviewed steel work.",
            "Needs review",
            "Inspection and repair records exist, but open NCR-005 means the reviewed set is "
            "not fully closed.",
            ("INSP-WELD-001", "NCR-005"),
            "bis-800-chunk-0007",
        ),
        _TopicProfile(
            "load-references",
            "The project load basis is demonstrated in enough detail for an engineering check.",
            "Needs review",
            "The register and calculation summary mention IS 875 and approved loads, but the "
            "indexed records do not show complete load combinations.",
            ("CODE-IS-875-2", "CODE-IS-875-3", "CALC-FRAME-03"),
            "bis-800-chunk-0001",
        ),
        _TopicProfile(
            "seismic-references",
            "Detailed seismic design evidence is present for the steel frame.",
            "Not evidenced",
            "The project register references IS 1893, but the available summary does not "
            "provide a detailed seismic design check.",
            ("CODE-IS-1893-1", "CALC-FRAME-06"),
            "bis-800-chunk-0001",
        ),
    ),
)

SUPPORTED_PROFILES = (IS_800_PROFILE,)


def _record_citation(record: ProjectRecord) -> Citation:
    return Citation(
        record_id=record.record_id,
        chunk_id=f"{record.record_id}-record",
        title=record.title,
        source_path=record.source_path,
        source_url=record.source_url,
        data_origin=record.data_origin,
    )


class StandardsEvidenceService:
    """Apply an explicit preview-topic profile to permitted project records."""

    def __init__(
        self,
        project_tools: ProjectTools,
        *,
        project_id: str,
        access_scopes: tuple[str, ...],
    ) -> None:
        self.project_tools = project_tools
        self.project_id = project_id
        self.access_scopes = access_scopes

    @staticmethod
    def _profile(standard: str) -> _StandardProfile:
        normalized = " ".join(standard.upper().split())
        for profile in SUPPORTED_PROFILES:
            if normalized in {" ".join(alias.upper().split()) for alias in profile.aliases}:
                return profile
        supported = ", ".join(profile.designation for profile in SUPPORTED_PROFILES)
        raise ValueError(
            f"No supported public-preview checklist for {standard}. Supported: {supported}"
        )

    def assess(self, standard: str) -> StandardEvidenceReport:
        from civil_copilot.agents.tools import ToolRequest

        profile = self._profile(standard)
        requested_ids = list(
            dict.fromkeys(
                [profile.project_record_id, profile.official_record_id]
                + [record_id for topic in profile.topics for record_id in topic.project_record_ids]
            )
        )
        try:
            observation = self.project_tools.call(
                ToolRequest(
                    tool_name="get_records",
                    arguments={"record_ids": requested_ids},
                    project_id=self.project_id,
                    access_scopes=list(self.access_scopes),
                )
            )
        except PermissionError as error:
            raise PermissionError(
                "Both permitted project records and the official public preview are required."
            ) from error

        records = {
            record.record_id: record
            for record in (
                ProjectRecord.model_validate(item) for item in observation.data.get("records", [])
            )
        }
        project_standard = records.get(profile.project_record_id)
        official = records.get(profile.official_record_id)
        if project_standard is None:
            raise PermissionError("The project standard reference is outside the permitted scope.")
        if official is None:
            raise PermissionError("The official public preview is outside the permitted scope.")

        rows: list[StandardEvidenceRow] = []
        for topic in profile.topics:
            available = [records[item] for item in topic.project_record_ids if item in records]
            status: EvidenceStatus = (
                topic.status if len(available) == len(topic.project_record_ids) else "Not evidenced"
            )
            reason = topic.reason
            if len(available) != len(topic.project_record_ids):
                missing = sorted(set(topic.project_record_ids) - records.keys())
                reason = f"The permitted project records are missing: {', '.join(missing)}."
            rows.append(
                StandardEvidenceRow(
                    topic_id=topic.topic_id,
                    topic=topic.topic,
                    status=status,
                    reason=reason,
                    project_evidence=[_record_citation(record) for record in available]
                    or [_record_citation(project_standard)],
                    official_source=Citation(
                        record_id=official.record_id,
                        chunk_id=topic.official_chunk_id,
                        title=official.title,
                        source_path=(
                            f"data/public/bis/academic/INDEX.jsonl#{topic.official_chunk_id}"
                        ),
                        source_url=official.source_url,
                        data_origin=official.data_origin,
                    ),
                )
            )
        return StandardEvidenceReport(
            project_id=self.project_id,
            standard=profile.designation,
            standard_record_id=profile.project_record_id,
            official_record_id=profile.official_record_id,
            rows=rows,
        )


def standards_report_answer(report: StandardEvidenceReport) -> AnswerResult:
    """Render the deterministic matrix in plain language without adding new claims."""

    sections = [f"IS 800 evidence review for project {report.project_id}"]
    for status in ("Evidenced", "Needs review", "Not evidenced", "Not applicable"):
        rows = [row for row in report.rows if row.status == status]
        if not rows:
            continue
        sections.append(f"**{status}**")
        sections.extend(
            f"- {row.topic} {row.reason} "
            f"[Project: {', '.join(item.record_id for item in row.project_evidence)}; "
            f"BIS preview: {row.official_source.chunk_id}]"
            for row in rows
        )
    sections.append(f"**Important limit:** {report.limitation}")
    serialized = list(
        dict.fromkeys(
            citation.model_dump_json()
            for row in report.rows
            for citation in [*row.project_evidence, row.official_source]
        )
    )
    return AnswerResult(
        answer="\n\n".join(sections),
        citations=[Citation.model_validate_json(item) for item in serialized],
        grounded=True,
        abstained=False,
        unsupported_claims=[],
    )
