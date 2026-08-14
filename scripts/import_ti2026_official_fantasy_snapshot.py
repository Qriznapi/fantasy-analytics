from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from tournament_config import resolve_event_db_path  # noqa: E402


REQUIRED_COLUMNS = {
    "snapshot_label",
    "role_slot",
    "official_name",
    "team_name",
    "official_position",
    "official_score",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import an official TI 2026 fantasy snapshot from CSV for comparison against local model outputs.")
    parser.add_argument("csv_path")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--source-label", default="official_client_manual")
    parser.add_argument("--replace-snapshot", action="store_true")
    return parser.parse_args()


def ensure_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ti2026_official_fantasy_snapshots (
            snapshot_label TEXT NOT NULL,
            role_slot TEXT NOT NULL,
            official_name TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_position INTEGER,
            official_score REAL NOT NULL,
            source_label TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            PRIMARY KEY (snapshot_label, role_slot, official_name, team_name)
        )
        """
    )
    con.commit()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
        return list(reader)


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_path)
    db_path = Path(args.db_path) if args.db_path else resolve_event_db_path("ti2026")
    rows = load_rows(csv_path)

    con = sqlite3.connect(str(db_path))
    try:
        ensure_table(con)
        snapshot_labels = sorted({row["snapshot_label"] for row in rows})
        if args.replace_snapshot:
            con.executemany(
                "DELETE FROM ti2026_official_fantasy_snapshots WHERE snapshot_label = ?",
                [(label,) for label in snapshot_labels],
            )
        con.executemany(
            """
            INSERT OR REPLACE INTO ti2026_official_fantasy_snapshots(
                snapshot_label, role_slot, official_name, team_name, official_position,
                official_score, source_label, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["snapshot_label"],
                    row["role_slot"],
                    row["official_name"],
                    row["team_name"],
                    int(row["official_position"]) if row["official_position"] else None,
                    float(row["official_score"]),
                    args.source_label,
                    row.get("notes", ""),
                )
                for row in rows
            ],
        )
        con.commit()
    finally:
        con.close()

    print(json.dumps({"db_path": str(db_path), "rows_imported": len(rows), "snapshot_labels": snapshot_labels}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
