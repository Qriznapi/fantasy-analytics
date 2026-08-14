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
            "foundation_reliability_runs",
            "foundation_reliability_entity_scores",
            "foundation_reliability_backtest",
            "analytics_reliable_players_foundation",
            "analytics_reliable_role_slots_foundation",
            "analytics_reliability_foundation_backtest",
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
            raise SystemExit(f"Missing reliability foundation objects: {missing}")
        runs = scalar(con, "SELECT COUNT(*) FROM foundation_reliability_runs")
        entity_rows = scalar(con, "SELECT COUNT(*) FROM foundation_reliability_entity_scores")
        backtest_rows = scalar(con, "SELECT COUNT(*) FROM foundation_reliability_backtest")
        if runs <= 0 or entity_rows <= 0:
            raise SystemExit("Reliability foundation layer is empty")
        print("reliability foundation validation ok")
        print(f"runs={runs}")
        print(f"entity_rows={entity_rows}")
        print(f"backtest_rows={backtest_rows}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
