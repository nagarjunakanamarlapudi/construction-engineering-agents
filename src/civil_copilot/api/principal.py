"""Deterministic server-owned principals for the academic demo API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

DEFAULT_DEMO_PRINCIPAL_ID = "reviewer"


class DemoPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True)

    principal_id: str
    user_id: str
    project_ids: tuple[str, ...]
    access_scopes: tuple[str, ...]

    def require_project(self, project_id: str) -> None:
        if project_id not in self.project_ids:
            raise PermissionError("The authenticated principal cannot access this project")


DEMO_PRINCIPALS: dict[str, DemoPrincipal] = {
    "reviewer": DemoPrincipal(
        principal_id="reviewer",
        user_id="reviewer",
        project_ids=("BLR-STEEL-DEMO",),
        access_scopes=("project:blr-steel-demo", "public"),
    ),
    "commercial-reviewer": DemoPrincipal(
        principal_id="commercial-reviewer",
        user_id="commercial-reviewer",
        project_ids=("BLR-STEEL-DEMO",),
        access_scopes=("project:blr-steel-demo", "public", "role:commercial"),
    ),
}

DEFAULT_DEMO_USER_ID = DEMO_PRINCIPALS[DEFAULT_DEMO_PRINCIPAL_ID].user_id
