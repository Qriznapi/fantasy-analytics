from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH, TARGET_SPECS  # noqa: E402


def scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(con.execute(sql, params).fetchone()[0])


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "ridge_prediction_runs",
            "ridge_prediction_outputs",
            "ridge_evaluation_reports",
            "analytics_prediction_ridge_evaluation",
        ]
        for name in required:
            row = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = ?",
                (name,),
            ).fetchone()
            if not row or int(row[0]) == 0:
                raise RuntimeError(f"Missing SQLite object: {name}")
        runs = scalar(con, "SELECT COUNT(*) FROM ridge_prediction_runs")
        outputs = scalar(con, "SELECT COUNT(*) FROM ridge_prediction_outputs")
        available_target_ids = {
            str(row[0])
            for row in con.execute("SELECT DISTINCT target_id FROM ridge_prediction_runs").fetchall()
        }
        for spec in TARGET_SPECS:
            if spec.target_id not in available_target_ids:
                raise RuntimeError(f"No ridge runs for target_id={spec.target_id}")
        print("prediction ridge validation ok")
        print(f"runs={runs}")
        print(f"outputs={outputs}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
