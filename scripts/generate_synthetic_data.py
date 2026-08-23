#!/usr/bin/env python3
"""Generate or validate the deterministic academic steel-building project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from civil_copilot.data.synthetic import (
    default_gold_scenarios,
    generate_demo_project,
    write_demo_project,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "synthetic" / "steel_building_demo"
SCENARIOS = ROOT / "data" / "evals" / "scenarios.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Validate generated data after writing it"
    )
    parser.add_argument("--seed", type=int, default=800)
    args = parser.parse_args()

    corpus = generate_demo_project(seed=args.seed)
    manifest = write_demo_project(corpus, OUTPUT)
    SCENARIOS.parent.mkdir(parents=True, exist_ok=True)
    SCENARIOS.write_text(
        json.dumps(
            [scenario.model_dump(mode="json") for scenario in default_gold_scenarios()],
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.check and manifest["dangling_relationship_count"]:
        raise SystemExit("Synthetic dataset contains dangling relationships")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
