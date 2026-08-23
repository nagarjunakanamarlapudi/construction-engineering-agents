#!/usr/bin/env python3
"""Refresh the approved official BIS public-preview collection."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "build_public_standards_index.py"),
        "--sources",
        str(ROOT / "data" / "public" / "bis" / "academic" / "SOURCES.json"),
        "--output-dir",
        str(ROOT / "data" / "public" / "bis" / "academic"),
    ]
    return subprocess.run(command, cwd=ROOT, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
