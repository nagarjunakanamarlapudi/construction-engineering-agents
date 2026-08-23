"""Stable repository paths for scripts, notebooks, tests, and local app composition."""

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
