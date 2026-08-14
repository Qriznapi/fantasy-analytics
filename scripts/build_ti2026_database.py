from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(SRC_DIR))

from build_event_database import bootstrap_event_database  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap the TI 2026 compact database from the shared event template.")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--template-db-path", default="")
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--skip-reference-seed", action="store_true")
    parser.add_argument("--load-live-data", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--limit-matches", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = bootstrap_event_database(
        "ti2026",
        db_path=Path(args.db_path) if args.db_path else None,
        template_db_path=Path(args.template_db_path) if args.template_db_path else None,
        replace_existing=args.replace_existing,
        skip_reference_seed=args.skip_reference_seed,
    )
    if args.load_live_data:
        from tournament_sync import sync_ti2026  # noqa: WPS433

        result["live_sync"] = sync_ti2026(
            db_path=Path(args.db_path) if args.db_path else None,
            sleep_sec=args.sleep_sec,
            timeout_sec=args.timeout_sec,
            limit_matches=args.limit_matches or None,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
