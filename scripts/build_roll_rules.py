from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fantasy_complex_banner_schema import ensure_complex_banner_schema, seed_default_complex_banner_templates  # noqa: E402
from fantasy_roll_simulator import seed_default_roll_distributions  # noqa: E402
from project_db import resolve_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed baseline roll rules and distributions for complex banners.")
    parser.add_argument("--event-id", default="ti2026", choices=["ewc2026", "ti2026"])
    parser.add_argument("--db-path", default="", help="Path to target SQLite database.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = resolve_db_path(PROJECT_ROOT, explicit=args.db_path or None, event_id=args.event_id)
    con = sqlite3.connect(str(db_path))
    try:
        ensure_complex_banner_schema(con)
        seed_default_complex_banner_templates(con)
        seed_default_roll_distributions(con)
        quality_count = con.execute("SELECT COUNT(*) FROM fantasy_banner_quality_rules").fetchone()[0]
        trait_count = con.execute("SELECT COUNT(*) FROM fantasy_banner_trait_rules").fetchone()[0]
        rule_count = con.execute("SELECT COUNT(*) FROM fantasy_banner_roll_rules").fetchone()[0]
        dist_count = con.execute("SELECT COUNT(*) FROM fantasy_banner_roll_distributions").fetchone()[0]
        con.commit()
    finally:
        con.close()
    print(
        json.dumps(
            {
                "db_path": str(db_path),
                "quality_rules": int(quality_count),
                "trait_rules": int(trait_count),
                "roll_rules": int(rule_count),
                "roll_distributions": int(dist_count),
                "status": "ok",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
