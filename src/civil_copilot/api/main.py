"""HTTP API shared by the Streamlit UI and automated evaluations."""

import logging
from contextlib import asynccontextmanager
from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from civil_copilot.agents.state import ChatRequest, ChatResponse
from civil_copilot.agents.tools import ToolRequest
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.api.principal import DEMO_PRINCIPALS, DemoPrincipal
from civil_copilot.config import Settings
from civil_copilot.data.models import GoldScenario
from civil_copilot.graph.service import GraphPath
from civil_copilot.memory.index import PostgresPreferenceIdIndex
from civil_copilot.memory.service import (
    InMemoryPreferenceBackend,
    Mem0PreferenceBackend,
    PreferenceMemory,
)
from civil_copilot.runtime import ApplicationRuntime, build_application_runtime
from civil_copilot.standards.service import StandardEvidenceReport, StandardsEvidenceService

LOGGER = logging.getLogger(__name__)


class PreferenceUpdate(BaseModel):
    project_id: str = Field(default="BLR-STEEL-DEMO", min_length=2, max_length=100)
    preference_type: str = Field(min_length=2, max_length=50)
    value: str = Field(min_length=2, max_length=50)


def build_memory(settings: Settings) -> PreferenceMemory:
    if not settings.mem0_api_key:
        return PreferenceMemory(InMemoryPreferenceBackend())
    api_key = settings.mem0_api_key.get_secret_value()
    try:
        backend = Mem0PreferenceBackend(
            api_key,
            preference_index=PostgresPreferenceIdIndex(str(settings.database_url)),
        )
    except (ValueError, OSError):
        LOGGER.warning("Mem0 is unavailable; using process-local preference memory")
        backend = InMemoryPreferenceBackend()
    return PreferenceMemory(backend)


@lru_cache
def build_application() -> ApplicationRuntime:
    settings = Settings()
    return build_application_runtime(
        mode=settings.copilot_runtime_mode,
        settings=settings,
    )


@lru_cache
def build_workflow() -> CopilotWorkflow:
    return build_application().workflow


def create_app(
    workflow: CopilotWorkflow | None = None,
    application_runtime: ApplicationRuntime | None = None,
    demo_principal_id: str = "reviewer",
) -> FastAPI:
    owns_runtime = workflow is None and application_runtime is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        owned = getattr(app.state, "owned_application_runtime", None)
        if owns_runtime and owned is not None:
            try:
                owned.close()
            finally:
                cache_clear = getattr(build_application, "cache_clear", None)
                if cache_clear is not None:
                    cache_clear()
                build_workflow.cache_clear()

    application = FastAPI(
        title="Civil Engineering Project Copilot",
        version="0.1.0",
        description=(
            "Grounded RAG, Graph RAG, and agentic investigation over a connected demo project."
        ),
        lifespan=lifespan,
    )

    def principal_dependency() -> DemoPrincipal:
        principal = DEMO_PRINCIPALS.get(demo_principal_id)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unknown demo principal")
        return principal

    def runtime_dependency() -> ApplicationRuntime | None:
        if application_runtime is not None:
            return application_runtime
        if workflow is not None:
            return None
        owned = getattr(application.state, "owned_application_runtime", None)
        if owned is None:
            owned = build_application()
            application.state.owned_application_runtime = owned
        return owned

    def dependency() -> CopilotWorkflow:
        if workflow is not None:
            return workflow
        if application_runtime is not None:
            return application_runtime.workflow
        runtime = runtime_dependency()
        assert runtime is not None
        return runtime.workflow

    @application.get("/health")
    def health(
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        runtime: Annotated[ApplicationRuntime | None, Depends(runtime_dependency)],
    ):
        capabilities = (
            runtime.capabilities.model_dump(mode="json")
            if runtime is not None
            else {
                "mode": "injected",
                "records_backend": "injected",
                "search_backend": "injected",
                "graph_backend": "injected",
                "server_filtered": False,
                "fallback_allowed": False,
            }
        )
        readiness = (
            runtime.readiness()
            if runtime is not None
            else {"records": "ready", "search": "ready", "graph": "ready"}
        )
        ready = all(value == "ready" for value in readiness.values())
        payload = {
            "status": "ok" if ready else "not_ready",
            "workflow": "ready",
            "orchestrator": type(service).__name__,
            "capabilities": capabilities,
            "readiness": readiness,
        }
        return payload if ready else JSONResponse(status_code=503, content=payload)

    @application.get("/api/scenarios", response_model=list[GoldScenario])
    def scenarios() -> list[GoldScenario]:
        from civil_copilot.data.synthetic import default_gold_scenarios

        return default_gold_scenarios()

    @application.post("/api/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
    ) -> ChatResponse:
        try:
            principal.require_project(request.project_id)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        scoped_request = request.model_copy(
            update={
                "user_id": principal.user_id,
                "access_scopes": list(principal.access_scopes),
            }
        )
        return service.invoke(scoped_request)

    @application.get("/api/memory/{user_id}")
    def get_memory(
        user_id: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
        project_id: str = "BLR-STEEL-DEMO",
    ) -> dict[str, str]:
        if user_id != principal.user_id:
            raise HTTPException(status_code=403, detail="Memory is scoped to the principal")
        try:
            principal.require_project(project_id)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        try:
            return service.memory.get(user_id, project_id)
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="Preference memory is unavailable"
            ) from error

    @application.post("/api/memory/{user_id}")
    def save_memory(
        user_id: str,
        update: PreferenceUpdate,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
    ) -> dict[str, str]:
        if user_id != principal.user_id:
            raise HTTPException(status_code=403, detail="Memory is scoped to the principal")
        try:
            principal.require_project(update.project_id)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        try:
            service.memory.add(
                user_id,
                update.project_id,
                update.preference_type,
                update.value,
            )
            return {update.preference_type: update.value.strip().lower()}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="Preference memory is unavailable"
            ) from error

    @application.get("/api/records")
    def records(
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        runtime: Annotated[ApplicationRuntime | None, Depends(runtime_dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
        record_type: str | None = None,
        status: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict]:
        project_id = principal.project_ids[0]
        if runtime is not None:
            visible = runtime.stores.records.query_records(
                project_id=project_id,
                access_scopes=list(principal.access_scopes),
                record_types=[record_type] if record_type else None,
                statuses=[status] if status else None,
                limit=limit,
            )
        else:
            visible = [
                record
                for record in service.tools.records.values()
                if record.project_id == project_id
                and bool(set(record.access_scopes) & set(principal.access_scopes))
                and (not record_type or record.record_type == record_type)
                and (not status or record.status == status)
            ]
        return [
            record.model_dump(mode="json")
            for record in sorted(visible, key=lambda item: item.record_id)[:limit]
        ]

    @application.get("/api/records/{record_id}")
    def record(
        record_id: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
    ) -> dict:
        try:
            observation = service.tools.call(
                ToolRequest(
                    tool_name="get_records",
                    arguments={"record_ids": [record_id.upper()]},
                    project_id=principal.project_ids[0],
                    access_scopes=list(principal.access_scopes),
                )
            )
        except PermissionError as error:
            raise HTTPException(status_code=404, detail="Unknown record") from error
        selected = observation.data.get("records", [])
        if not selected:
            raise HTTPException(status_code=404, detail=f"Unknown record {record_id.upper()}")
        return selected[0]

    @application.get("/api/standards/evidence", response_model=StandardEvidenceReport)
    def standard_evidence(
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
        standard: str = "IS 800:2007",
    ) -> StandardEvidenceReport:
        try:
            return StandardsEvidenceService(
                service.tools,
                project_id=principal.project_ids[0],
                access_scopes=principal.access_scopes,
            ).assess(standard)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/graph/{record_id}")
    def graph(
        record_id: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
        max_depth: Annotated[int, Query(ge=1, le=5)] = 2,
        as_of_date: date | None = None,
    ) -> dict[str, str | int | list[GraphPath]]:
        try:
            observation = service.tools.call(
                ToolRequest(
                    tool_name="find_graph_paths",
                    arguments={
                        "start_id": record_id.upper(),
                        "max_depth": max_depth,
                        "as_of_date": as_of_date,
                    },
                    project_id=principal.project_ids[0],
                    access_scopes=list(principal.access_scopes),
                )
            )
            paths = observation.graph_paths
        except (KeyError, PermissionError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"record_id": record_id.upper(), "max_depth": max_depth, "paths": paths}

    @application.get("/api/compare/{document_number}")
    def compare(
        document_number: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        principal: Annotated[DemoPrincipal, Depends(principal_dependency)],
    ) -> dict[str, str | list[dict]]:
        normalized = document_number.upper()
        observation = service.tools.call(
            ToolRequest(
                tool_name="compare_revisions",
                arguments={"document_number": normalized},
                project_id=principal.project_ids[0],
                access_scopes=list(principal.access_scopes),
            )
        )
        revisions = observation.data.get("records", [])
        if not revisions:
            raise HTTPException(status_code=404, detail=f"Unknown drawing {normalized}")
        return {
            "document_number": normalized,
            "revisions": [
                record
                for record in sorted(revisions, key=lambda item: str(item.get("revision", "")))
            ],
        }

    return application


app = create_app()
