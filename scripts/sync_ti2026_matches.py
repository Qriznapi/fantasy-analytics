from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from report_ti2026_status import build_status, render_markdown  # noqa: E402
from tournament_sync import sync_ti2026  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and load current TI 2026 matches, rosters, and fantasy inputs into the TI database.")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--limit-matches", type=int, default=0)
    parser.add_argument("--write-status-report", action="store_true")
    parser.add_argument("--status-report-path", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = sync_ti2026(
        db_path=Path(args.db_path) if args.db_path else None,
        sleep_sec=args.sleep_sec,
        timeout_sec=args.timeout_sec,
        limit_matches=args.limit_matches or None,
    )
    if args.write_status_report:
        db_path = Path(args.db_path) if args.db_path else Path(result["db_path"])
        status = build_status(db_path)
        report_path = Path(args.status_report_path) if args.status_report_path else PROJECT_ROOT / "reports" / "ti2026_status.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_markdown(status), encoding="utf-8")
        result["status_report_path"] = str(report_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
