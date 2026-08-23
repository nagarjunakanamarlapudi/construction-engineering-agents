"""HTTP API shared by the Streamlit UI and automated evaluations."""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from civil_copilot.agents.router import LLMQuestionRouter
from civil_copilot.agents.state import ChatRequest, ChatResponse
from civil_copilot.agents.tools import ProjectTools
from civil_copilot.agents.workflow import CopilotWorkflow
from civil_copilot.config import Settings
from civil_copilot.data.loaders import load_corpus
from civil_copilot.data.models import GoldScenario
from civil_copilot.demo import build_offline_workflow
from civil_copilot.graph.service import GraphPath, ProjectGraphService
from civil_copilot.memory.service import (
    InMemoryPreferenceBackend,
    Mem0PreferenceBackend,
    PreferenceMemory,
)
from civil_copilot.observability.tracing import create_tracing
from civil_copilot.retrieval.hybrid import HybridRetriever
from civil_copilot.stores.qdrant import OpenAIEmbedding, QdrantSearchStore

ROOT = Path(__file__).resolve().parents[3]
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
        backend = Mem0PreferenceBackend(api_key)
    except (ValueError, OSError):
        LOGGER.warning("Mem0 is unavailable; using process-local preference memory")
        backend = InMemoryPreferenceBackend()
    return PreferenceMemory(backend)


@lru_cache
def build_workflow() -> CopilotWorkflow:
    settings = Settings()
    corpus = load_corpus(ROOT)
    offline = build_offline_workflow(corpus)
    vector_search = offline.tools.retriever.vector_search
    if settings.openai_api_key:
        try:
            search_store = QdrantSearchStore(
                str(settings.qdrant_url),
                OpenAIEmbedding(
                    settings.openai_api_key.get_secret_value(), settings.openai_embedding_model
                ),
                api_key=(
                    settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
                ),
            )
            if search_store.count() > 0:
                vector_search = search_store.search
        except Exception as error:
            # The portable offline index keeps notebooks/API usable before Docker is started.
            LOGGER.warning("Using portable vector fallback: %s", type(error).__name__)
    tools = ProjectTools(
        corpus.records,
        HybridRetriever(corpus.chunks, vector_search),
        ProjectGraphService(corpus.records, corpus.relationships),
    )
    router = None
    if settings.openai_api_key:
        router = LLMQuestionRouter.from_openai(
            settings.openai_api_key.get_secret_value(), settings.openai_model
        )
    return CopilotWorkflow(
        tools,
        router=router,
        tracing=create_tracing(settings),
        memory=build_memory(settings),
    )


def create_app(workflow: CopilotWorkflow | None = None) -> FastAPI:
    application = FastAPI(
        title="Civil Engineering Project Copilot",
        version="0.1.0",
        description=(
            "Grounded RAG, Graph RAG, and agentic investigation over a connected demo project."
        ),
    )

    def dependency() -> CopilotWorkflow:
        return workflow or build_workflow()

    @application.get("/health")
    def health(
        service: Annotated[CopilotWorkflow, Depends(dependency)],
    ) -> dict[str, str]:
        return {"status": "ok", "workflow": "ready", "orchestrator": type(service).__name__}

    @application.get("/api/scenarios", response_model=list[GoldScenario])
    def scenarios() -> list[GoldScenario]:
        from civil_copilot.data.synthetic import default_gold_scenarios

        return default_gold_scenarios()

    @application.post("/api/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
    ) -> ChatResponse:
        return service.invoke(request)

    @application.get("/api/memory/{user_id}")
    def get_memory(
        user_id: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        project_id: str = "BLR-STEEL-DEMO",
    ) -> dict[str, str]:
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
    ) -> dict[str, str]:
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
        record_type: str | None = None,
        status: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict]:
        visible = [
            record
            for record in service.tools.records.values()
            if record.project_id == "BLR-STEEL-DEMO"
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
    ) -> dict:
        selected = service.tools.records.get(record_id.upper())
        if not selected:
            raise HTTPException(status_code=404, detail=f"Unknown record {record_id.upper()}")
        return selected.model_dump(mode="json")

    @application.get("/api/graph/{record_id}")
    def graph(
        record_id: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
        max_depth: Annotated[int, Query(ge=1, le=5)] = 2,
    ) -> dict[str, str | int | list[GraphPath]]:
        try:
            paths = service.tools.graph.find_paths(record_id.upper(), max_depth=max_depth)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"record_id": record_id.upper(), "max_depth": max_depth, "paths": paths}

    @application.get("/api/compare/{document_number}")
    def compare(
        document_number: str,
        service: Annotated[CopilotWorkflow, Depends(dependency)],
    ) -> dict[str, str | list[dict]]:
        normalized = document_number.upper()
        revisions = [
            record
            for record in service.tools.records.values()
            if record.record_type == "drawing"
            and str(record.metadata.get("document_number", "")).upper() == normalized
        ]
        if not revisions:
            raise HTTPException(status_code=404, detail=f"Unknown drawing {normalized}")
        return {
            "document_number": normalized,
            "revisions": [
                record.model_dump(mode="json")
                for record in sorted(revisions, key=lambda item: item.revision)
            ],
        }

    return application


app = create_app()
