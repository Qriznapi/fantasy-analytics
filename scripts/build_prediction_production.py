from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_production import build_prediction_production  # noqa: E402


def main() -> None:
    result = build_prediction_production()
    print(f"profile_id={result['profile_id']}")
    print(result["choices"].to_string(index=False))


if __name__ == "__main__":
    main()
