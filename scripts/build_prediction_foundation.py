from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import build_prediction_foundation  # noqa: E402


def main() -> None:
    result = build_prediction_foundation()
    print(f"profile_id={result['profile_id']}")
    print(f"target_rows={result['target_rows']}")
    print(f"foundation_runs={len(result['run_ids'])}")
    print()
    summary = result["summary"]
    if summary.empty:
        print("No foundation summary rows were produced.")
        return
    print("Top foundation rows by target/split:")
    print(summary.groupby(["target_id", "split_name"], sort=False).head(3).to_string(index=False))


if __name__ == "__main__":
    main()
