from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


def scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> int | float:
    return con.execute(sql, params).fetchone()[0]


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "stat_signal_summary",
            "stat_synergy_matrix",
            "analytics_stat_signal_summary",
            "analytics_stat_synergy_matrix",
        ]
        missing = [
            name
            for name in required
            if scalar(
                con,
                "SELECT COUNT(*) FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
                (name,),
            )
            == 0
        ]
        if missing:
            raise SystemExit(f"Missing stat synergy objects: {missing}")
        signal_rows = scalar(con, "SELECT COUNT(*) FROM stat_signal_summary")
        synergy_rows = scalar(con, "SELECT COUNT(*) FROM stat_synergy_matrix")
        if signal_rows <= 0 or synergy_rows <= 0:
            raise SystemExit("Stat synergy layer is empty")
        print("stat synergy validation ok")
        print(f"signal_rows={signal_rows}")
        print(f"synergy_rows={synergy_rows}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
