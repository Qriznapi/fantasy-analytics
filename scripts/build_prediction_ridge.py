from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_ridge import build_prediction_ridge  # noqa: E402


def main() -> None:
    result = build_prediction_ridge()
    print(f"profile_id={result['profile_id']}")
    print(f"run_count={len(result['run_ids'])}")
    if not result["selected_alphas"].empty:
        print(result["selected_alphas"].to_string(index=False))
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
