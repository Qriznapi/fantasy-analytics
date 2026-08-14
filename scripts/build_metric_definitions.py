from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_metric_definitions import build_metric_definitions  # noqa: E402


def main() -> None:
    count = build_metric_definitions()
    print(f"metric_definitions={count}")


if __name__ == "__main__":
    main()
