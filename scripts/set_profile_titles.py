from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from fantasy_profile_constructor import ensure_title_schema, set_profile_title_rules  # noqa: E402
from tournament_config import resolve_event_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assign coach title rules to a fantasy scoring profile.")
    parser.add_argument("--event-id", choices=["ewc2026", "ti2026"], default="ti2026")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--profile-id", required=True)
    parser.add_argument(
        "--input-json",
        required=True,
        help="Path to JSON file with a list of title rule objects.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path) if args.db_path else resolve_event_db_path(args.event_id)
    title_spec = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    if not isinstance(title_spec, list):
        raise SystemExit("input-json must contain a JSON list of title rules")

    con = sqlite3.connect(str(db_path))
    try:
        ensure_title_schema(con)
        set_profile_title_rules(con, args.profile_id, title_spec, commit=True)
        rows = con.execute(
            """
            SELECT profile_id, title_slot, title_name, role_scope, bonus_pct,
                   condition_metric, condition_operator, condition_value, enabled
            FROM fantasy_scoring_profile_titles
            WHERE profile_id = ?
            ORDER BY title_slot
            """,
            (args.profile_id,),
        ).fetchall()
    finally:
        con.close()

    print(
        json.dumps(
            {
                "db_path": str(db_path),
                "profile_id": args.profile_id,
                "title_rules": [list(row) for row in rows],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
