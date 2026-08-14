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
            "foundation_optimizer_v2_runs",
            "foundation_optimizer_v2_recommendations",
            "foundation_optimizer_v2_backtest",
            "foundation_optimizer_v2_evaluation_reports",
            "analytics_optimizer_v2_players",
            "analytics_optimizer_v2_role_slots",
            "analytics_optimizer_v2_backtest",
            "analytics_optimizer_v2_evaluation",
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
            raise SystemExit(f"Missing optimizer v2 objects: {missing}")
        runs = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_v2_runs")
        recs = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_v2_recommendations")
        backtest = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_v2_backtest")
        eval_rows = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_v2_evaluation_reports")
        if runs <= 0 or recs <= 0 or backtest <= 0 or eval_rows <= 0:
            raise SystemExit("Optimizer v2 layer is empty")
        print("optimizer v2 validation ok")
        print(f"runs={runs}")
        print(f"recommendations={recs}")
        print(f"backtest_rows={backtest}")
        print(f"evaluation_rows={eval_rows}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
