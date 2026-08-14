from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH, TARGET_SPECS  # noqa: E402


def scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> int | float:
    return con.execute(sql, params).fetchone()[0]


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "prediction_target_registry",
            "dataset_prediction_targets",
            "foundation_model_registry",
            "foundation_prediction_runs",
            "foundation_prediction_outputs",
            "foundation_evaluation_reports",
            "analytics_prediction_foundation_evaluation",
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
            raise SystemExit(f"Missing foundation objects: {missing}")

        target_rows = scalar(con, "SELECT COUNT(*) FROM dataset_prediction_targets")
        runs = scalar(con, "SELECT COUNT(*) FROM foundation_prediction_runs")
        outputs = scalar(con, "SELECT COUNT(*) FROM foundation_prediction_outputs")
        reports = scalar(con, "SELECT COUNT(*) FROM foundation_evaluation_reports")
        if target_rows <= 0 or runs <= 0 or outputs <= 0 or reports <= 0:
            raise SystemExit("Foundation layer was not populated")

        for spec in TARGET_SPECS:
            count = scalar(
                con,
                "SELECT COUNT(*) FROM dataset_prediction_targets WHERE target_id = ?",
                (spec.target_id,),
            )
            if count <= 0:
                raise SystemExit(f"No rows found for target_id={spec.target_id}")

        print("prediction foundation validation ok")
        print(f"target_rows={target_rows}")
        print(f"runs={runs}")
        print(f"outputs={outputs}")
        print(f"reports={reports}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
