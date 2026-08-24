from datetime import date

from civil_copilot.data.models import ProjectRecord, Relationship
from civil_copilot.data.synthetic import generate_demo_project
from civil_copilot.schedule.service import ScheduleImpactService


def _activity(record_id: str, *, critical: bool, total_float_days: int) -> ProjectRecord:
    return ProjectRecord(
        record_id=record_id,
        project_id="BLR-STEEL-DEMO",
        record_type="schedule_activity",
        title=record_id,
        content=f"Planned activity {record_id}.",
        status="planned",
        revision="baseline-1",
        effective_date=date(2026, 1, 1),
        data_origin="synthetic_academic_demo",
        source_path=f"test/{record_id}",
        access_scopes=["project:blr-steel-demo"],
        metadata={"critical": critical, "total_float_days": total_float_days},
    )


def _depends_on(successor: str, predecessor: str) -> Relationship:
    return Relationship(
        relationship_id=f"{successor}-depends-on-{predecessor}",
        project_id="BLR-STEEL-DEMO",
        source_id=successor,
        target_id=predecessor,
        relationship_type="DEPENDS_ON",
        provenance="test schedule",
        method="synthetic_test",
        confidence=1.0,
        valid_from=date(2026, 1, 1),
    )


def test_schedule_impact_consumes_float_then_propagates_residual_delay_downstream():
    records = [
        _activity("ACT-A", critical=False, total_float_days=2),
        _activity("ACT-B", critical=True, total_float_days=0),
        _activity("ACT-C", critical=False, total_float_days=1),
    ]
    relationships = [_depends_on("ACT-B", "ACT-A"), _depends_on("ACT-C", "ACT-B")]
    service = ScheduleImpactService(records, relationships=relationships)

    result = service.analyze(["ACT-A"], delay_days=5)

    assert result.float_days_by_activity == {"ACT-A": 2, "ACT-B": 0, "ACT-C": 1}
    assert result.projected_delay_days_by_activity == {"ACT-A": 3, "ACT-B": 3, "ACT-C": 2}
    assert result.downstream_activity_ids == ["ACT-B", "ACT-C"]
    assert result.impacted_activity_ids == ["ACT-A", "ACT-B", "ACT-C"]
    assert result.critical_activity_ids == ["ACT-B"]
    assert result.projected_critical_delay_days == 3
    assert result.source_ids == ["ACT-A", "ACT-B", "ACT-C"]


def test_schedule_impact_respects_relationship_effective_date():
    records = [
        _activity("ACT-A", critical=True, total_float_days=0),
        _activity("ACT-B", critical=True, total_float_days=0),
    ]
    future = _depends_on("ACT-B", "ACT-A").model_copy(update={"valid_from": date(2030, 1, 1)})
    service = ScheduleImpactService(records, relationships=[future])

    result = service.analyze(["ACT-A"], delay_days=4, as_of_date=date(2026, 1, 1))

    assert result.downstream_activity_ids == []
    assert result.projected_delay_days_by_activity == {"ACT-A": 4}


def test_demo_schedule_has_connected_float_aware_impact_evidence():
    corpus = generate_demo_project(seed=800)
    service = ScheduleImpactService(corpus.records, relationships=corpus.relationships)

    result = service.analyze(["ACT-STEEL-009"], delay_days=5)

    assert result.downstream_activity_ids[:2] == ["ACT-STEEL-010", "ACT-STEEL-011"]
    assert result.projected_delay_days_by_activity["ACT-STEEL-011"] == 5
    assert result.projected_delay_days_by_activity["ACT-STEEL-012"] == 3
    assert result.projected_critical_delay_days == 5
