from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_stat_synergy import build_stat_synergy  # noqa: E402


def main() -> None:
    result = build_stat_synergy()
    print(f"profile_id={result['profile_id']}")
    print(f"signal_rows={result['signal_rows']}")
    print(f"synergy_rows={result['synergy_rows']}")
    print()
    if result["top_pairs"].empty:
        print("No synergy rows were produced.")
        return
    print("Top synergy pairs:")
    print(result["top_pairs"].to_string(index=False))


if __name__ == "__main__":
    main()
