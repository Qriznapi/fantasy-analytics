from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_baselines import (  # noqa: E402
    DB_PATH,
    PLAYER_SERIES_TARGET,
    ROLE_SLOT_SERIES_TARGET,
)


def scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> int | float:
    return con.execute(sql, params).fetchone()[0]


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "dataset_player_series_targets",
            "dataset_role_slot_series_targets",
            "baseline_model_registry",
            "baseline_prediction_runs",
            "baseline_prediction_outputs",
            "baseline_evaluation_reports",
            "analytics_baseline_evaluation",
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
            raise SystemExit(f"Missing baseline objects: {missing}")

        player_rows = scalar(con, "SELECT COUNT(*) FROM dataset_player_series_targets")
        role_rows = scalar(con, "SELECT COUNT(*) FROM dataset_role_slot_series_targets")
        runs = scalar(con, "SELECT COUNT(*) FROM baseline_prediction_runs")
        outputs = scalar(con, "SELECT COUNT(*) FROM baseline_prediction_outputs")
        reports = scalar(con, "SELECT COUNT(*) FROM baseline_evaluation_reports")

        if player_rows <= 0 or role_rows <= 0:
            raise SystemExit("Baseline datasets are empty")
        if runs <= 0 or outputs <= 0 or reports <= 0:
            raise SystemExit("Baseline runs were not populated")

        for target_type in (PLAYER_SERIES_TARGET, ROLE_SLOT_SERIES_TARGET):
            count = scalar(
                con,
                "SELECT COUNT(*) FROM baseline_prediction_runs WHERE target_type = ?",
                (target_type,),
            )
            if count <= 0:
                raise SystemExit(f"No runs found for target_type={target_type}")

        print("baseline validation ok")
        print(f"player_series_rows={player_rows}")
        print(f"role_slot_series_rows={role_rows}")
        print(f"runs={runs}")
        print(f"outputs={outputs}")
        print(f"reports={reports}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
