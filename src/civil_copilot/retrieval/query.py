"""Question-time filters and access context."""

from typing import Any

from pydantic import BaseModel, Field


class QueryContext(BaseModel):
    question: str = Field(min_length=2)
    project_id: str = "BLR-STEEL-DEMO"
    access_scopes: list[str] = Field(default_factory=lambda: ["project:blr-steel-demo", "public"])
    top_k: int = Field(default=6, ge=1, le=20)
    minimum_rerank_score: float = Field(default=0.025, ge=0)
    filters: dict[str, Any] = Field(default_factory=dict)
