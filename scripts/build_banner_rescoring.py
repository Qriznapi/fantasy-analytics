from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_banner_rescoring import build_banner_rescoring  # noqa: E402


def main() -> None:
    result = build_banner_rescoring()
    print(f"profile_id={result['profile_id']}")
    print(f"run_count={len(result['run_ids'])}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
