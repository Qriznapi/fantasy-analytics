from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from validate_event_database import validate_event_database  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the TI 2026 database bootstrap.")
    parser.add_argument("--db-path", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_event_database("ti2026", db_path=Path(args.db_path) if args.db_path else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
