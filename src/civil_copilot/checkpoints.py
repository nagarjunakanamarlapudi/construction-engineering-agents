"""LangGraph checkpoint resources with an explicit durability boundary."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver


@dataclass
class CheckpointResources:
    """Own one checkpointer and, when applicable, its database connection."""

    saver: BaseCheckpointSaver
    backend: Literal["memory", "postgresql"]
    durable: bool
    _manager: AbstractContextManager[PostgresSaver] | None = field(
        default=None,
        repr=False,
    )
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        if self._manager is not None:
            self._manager.__exit__(None, None, None)
        self._closed = True


def create_checkpoint_resources(
    *,
    mode: str,
    database_url: str | None = None,
) -> CheckpointResources:
    """Create process-local checkpoints for portable mode or durable PostgreSQL otherwise."""

    if mode == "portable":
        return CheckpointResources(
            saver=InMemorySaver(),
            backend="memory",
            durable=False,
        )
    if mode not in {"local", "live"}:
        raise ValueError(f"unknown checkpoint mode: {mode}")
    if not database_url:
        raise ValueError(f"{mode} checkpoint mode requires database_url")

    manager = PostgresSaver.from_conn_string(database_url)
    saver = manager.__enter__()
    try:
        # LangGraph's setup migration is idempotent and safe to run at startup.
        saver.setup()
    except BaseException:
        manager.__exit__(*sys.exc_info())
        raise
    return CheckpointResources(
        saver=saver,
        backend="postgresql",
        durable=True,
        _manager=manager,
    )
