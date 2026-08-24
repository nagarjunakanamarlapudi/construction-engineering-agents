"""Read-only, deterministic schedule scenario calculations."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import date

from pydantic import BaseModel, Field

from civil_copilot.data.models import ProjectRecord, Relationship


class ScheduleImpactResult(BaseModel):
    activity_ids: list[str]
    delay_days: int = Field(ge=0)
    critical_activity_ids: list[str]
    projected_critical_delay_days: int = Field(ge=0)
    downstream_activity_ids: list[str] = Field(default_factory=list)
    impacted_activity_ids: list[str] = Field(default_factory=list)
    float_days_by_activity: dict[str, int] = Field(default_factory=dict)
    projected_delay_days_by_activity: dict[str, int] = Field(default_factory=dict)
    source_ids: list[str]
    as_of_date: date | None = None


class ScheduleImpactService:
    def __init__(
        self,
        records: list[ProjectRecord],
        *,
        relationships: list[Relationship] | None = None,
    ) -> None:
        self.records = {record.record_id: record for record in records}
        self.relationships = list(relationships or [])

    @staticmethod
    def _float_days(record: ProjectRecord) -> int:
        value = record.metadata.get("total_float_days")
        if value is None:
            return 0 if bool(record.metadata.get("critical", False)) else 0
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"invalid total_float_days for schedule activity {record.record_id}"
            ) from error
        if parsed < 0:
            raise ValueError(
                f"total_float_days cannot be negative for schedule activity {record.record_id}"
            )
        return parsed

    def _successors(self, as_of_date: date | None) -> dict[str, list[str]]:
        successors: dict[str, set[str]] = defaultdict(set)
        for relationship in self.relationships:
            if relationship.relationship_type != "DEPENDS_ON":
                continue
            if as_of_date is not None and relationship.valid_from > as_of_date:
                continue
            successor = self.records.get(relationship.source_id)
            predecessor = self.records.get(relationship.target_id)
            if not successor or not predecessor:
                continue
            if successor.record_type != "schedule_activity":
                continue
            if predecessor.record_type != "schedule_activity":
                continue
            successors[predecessor.record_id].add(successor.record_id)
        return {record_id: sorted(values) for record_id, values in successors.items()}

    def analyze(
        self,
        activity_ids: list[str],
        *,
        delay_days: int,
        as_of_date: date | None = None,
    ) -> ScheduleImpactResult:
        if not activity_ids:
            raise ValueError("at least one activity is required")
        if not 0 <= delay_days <= 3650:
            raise ValueError("delay_days must be between 0 and 3650")
        selected: list[ProjectRecord] = []
        for activity_id in dict.fromkeys(activity_ids):
            record = self.records.get(activity_id)
            if not record or record.record_type != "schedule_activity":
                raise ValueError(f"unknown schedule activity: {activity_id}")
            if as_of_date is not None and record.effective_date > as_of_date:
                raise ValueError(f"schedule activity {activity_id} is not effective as of date")
            selected.append(record)
        selected_ids = [record.record_id for record in selected]
        successor_map = self._successors(as_of_date)
        projected_delay: dict[str, int] = {}
        queue: deque[str] = deque()
        for record in selected:
            residual = max(delay_days - self._float_days(record), 0)
            projected_delay[record.record_id] = residual
            if residual > 0:
                queue.append(record.record_id)

        while queue:
            predecessor_id = queue.popleft()
            predecessor_delay = projected_delay[predecessor_id]
            for successor_id in successor_map.get(predecessor_id, []):
                successor = self.records[successor_id]
                residual = max(predecessor_delay - self._float_days(successor), 0)
                if residual <= projected_delay.get(successor_id, -1):
                    continue
                projected_delay[successor_id] = residual
                if residual > 0:
                    queue.append(successor_id)

        impacted = [record_id for record_id, days in projected_delay.items() if days > 0]
        downstream = [record_id for record_id in impacted if record_id not in selected_ids]
        relevant_ids = list(dict.fromkeys([*selected_ids, *downstream]))
        critical = [
            record_id
            for record_id in impacted
            if bool(self.records[record_id].metadata.get("critical", False))
        ]
        return ScheduleImpactResult(
            activity_ids=selected_ids,
            delay_days=delay_days,
            critical_activity_ids=critical,
            projected_critical_delay_days=max(
                (projected_delay[record_id] for record_id in critical), default=0
            ),
            downstream_activity_ids=downstream,
            impacted_activity_ids=impacted,
            float_days_by_activity={
                record_id: self._float_days(self.records[record_id]) for record_id in relevant_ids
            },
            projected_delay_days_by_activity={
                record_id: projected_delay[record_id] for record_id in relevant_ids
            },
            source_ids=relevant_ids,
            as_of_date=as_of_date,
        )
