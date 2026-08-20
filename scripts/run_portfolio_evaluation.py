"""Produce a reproducible matched-evaluation report for portfolio metrics."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "models" / "rng_neural_slot_selfplay_selected_v1.pt"
DEFAULT_DB = ROOT / "data" / "ti_2026_fantasy_compact.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a candidate against the active baseline on matched seeds.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--profile-id", default="ti2026_playoff_observed_nothingtogay_v1")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "portfolio_evaluation.json")
    args = parser.parse_args()
    for path in (args.candidate, args.baseline, args.db_path):
        if not path.exists():
            raise SystemExit(f"Missing local evaluation artifact: {path}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(ROOT / "scripts" / "evaluate_rng_planner_actors.py"),
        "--db-path", str(args.db_path), "--profile-id", args.profile_id,
        "--base-artifact", str(args.baseline), "--candidate-artifact", str(args.candidate),
        "--episodes", str(args.episodes), "--seed", str(args.seed),
        "--output-json", str(args.output),
    ]
    subprocess.run(command, check=True)
    payload = json.loads(args.output.read_text(encoding="utf-8"))
    summary = payload.get("summary", payload)
    print("\n## Key Results (fresh matched evaluation)")
    print(f"- Evaluation episodes: {args.episodes}")
    for key in ("mean_delta", "median_delta", "win_rate", "bootstrap_ci_low", "bootstrap_ci_high"):
        if key in summary:
            print(f"- {key}: {summary[key]}")
    print(f"- Seed: {args.seed}")
    print(f"- Report: {args.output}")


if __name__ == "__main__":
    main()
