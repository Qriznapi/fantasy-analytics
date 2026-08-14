from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_reliability_foundation import build_reliability_foundation  # noqa: E402


def main() -> None:
    result = build_reliability_foundation()
    print(f"profile_id={result['profile_id']}")
    print(f"reliability_runs={len(result['run_ids'])}")
    print()
    summary = result["summary"]
    if summary.empty:
        print("No reliability foundation rows were produced.")
        return
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
