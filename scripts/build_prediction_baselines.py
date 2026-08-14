from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_baselines import build_prediction_baselines  # noqa: E402


def main() -> None:
    result = build_prediction_baselines()
    summary = result["summary"]
    print(f"profile_id={result['profile_id']}")
    print(f"player_series_rows={result['player_rows']}")
    print(f"role_slot_series_rows={result['role_slot_rows']}")
    print(f"baseline_runs={len(result['run_ids'])}")
    print()
    if summary.empty:
        print("No baseline summary rows were produced.")
        return
    print("Top baseline rows by target/split:")
    print(summary.groupby(["target_type", "split_name"], sort=False).head(3).to_string(index=False))


if __name__ == "__main__":
    main()
