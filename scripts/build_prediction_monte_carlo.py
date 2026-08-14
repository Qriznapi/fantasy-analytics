from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_monte_carlo import build_prediction_monte_carlo  # noqa: E402


def main() -> None:
    result = build_prediction_monte_carlo()
    print(f"rows_written={result['rows_written']}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
