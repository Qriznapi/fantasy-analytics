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
            "foundation_optimizer_runs",
            "foundation_optimizer_recommendations",
            "foundation_optimizer_backtest",
            "foundation_optimizer_evaluation_reports",
            "foundation_optimizer_baseline_reports",
            "analytics_optimizer_players_foundation",
            "analytics_optimizer_role_slots_foundation",
            "analytics_optimizer_foundation_backtest",
            "analytics_optimizer_foundation_evaluation",
            "analytics_optimizer_foundation_baselines",
            "metric_definitions",
            "analytics_metric_definitions",
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
            raise SystemExit(f"Missing optimizer/metric objects: {missing}")
        runs = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_runs")
        recs = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_recommendations")
        backtest = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_backtest")
        eval_rows = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_evaluation_reports")
        baseline_rows = scalar(con, "SELECT COUNT(*) FROM foundation_optimizer_baseline_reports")
        defs = scalar(con, "SELECT COUNT(*) FROM metric_definitions")
        if runs <= 0 or recs <= 0 or backtest <= 0 or eval_rows <= 0 or baseline_rows <= 0 or defs <= 0:
            raise SystemExit("Foundation optimizer or metric definitions are empty")
        print("foundation optimizer validation ok")
        print(f"runs={runs}")
        print(f"recommendations={recs}")
        print(f"backtest_rows={backtest}")
        print(f"evaluation_rows={eval_rows}")
        print(f"baseline_rows={baseline_rows}")
        print(f"metric_definitions={defs}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
