from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from tournament_config import load_tournament_config, resolve_event_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an event database bootstrap before ingestion work starts.")
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--db-path", default="")
    return parser.parse_args()


def validate_event_database(event_id: str, *, db_path: Path | None = None) -> dict[str, object]:
    config = load_tournament_config(event_id)
    path = db_path or resolve_event_db_path(event_id)
    if not path.exists():
        raise FileNotFoundError(f"Database does not exist yet: {path}")

    con = sqlite3.connect(str(path))
    try:
        bootstrap_tables = [
            "event_registry",
            "event_build_runs",
            "event_sync_runs",
            "event_sync_match_log",
        ]
        reference_tables = [
            "matches",
            "player_identity_registry",
            "fantasy_scoring_profiles",
            "fantasy_scoring_profile_stats",
        ]
        all_tables = bootstrap_tables + reference_tables
        missing = [
            table_name
            for table_name in all_tables
            if con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            is None
        ]
        if missing:
            raise RuntimeError(f"Database {path} is missing required bootstrap/reference tables: {missing}")

        registry_row = con.execute(
            "SELECT event_id, display_name, config_path FROM event_registry WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        build_runs = int(con.execute("SELECT COUNT(*) FROM event_build_runs WHERE event_id = ?", (event_id,)).fetchone()[0])
        profile_rows = int(con.execute("SELECT COUNT(*) FROM fantasy_scoring_profiles").fetchone()[0])
        profile_stat_rows = int(con.execute("SELECT COUNT(*) FROM fantasy_scoring_profile_stats").fetchone()[0])
        match_rows = int(con.execute("SELECT COUNT(*) FROM matches").fetchone()[0])
        identity_rows = int(con.execute("SELECT COUNT(*) FROM player_identity_registry").fetchone()[0])
        public_views = int(
            con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name LIKE 'analytics_%'").fetchone()[0]
        )
    finally:
        con.close()

    return {
        "event_id": event_id,
        "display_name": config.display_name,
        "db_path": str(path),
        "event_registry_row": list(registry_row) if registry_row else None,
        "build_runs": build_runs,
        "fantasy_scoring_profiles": profile_rows,
        "fantasy_scoring_profile_stats": profile_stat_rows,
        "matches": match_rows,
        "player_identity_registry": identity_rows,
        "analytics_views": public_views,
        "status": "ok",
    }


def main() -> None:
    args = parse_args()
    result = validate_event_database(args.event_id, db_path=Path(args.db_path) if args.db_path else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
