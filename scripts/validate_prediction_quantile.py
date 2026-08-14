from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH, TARGET_SPECS  # noqa: E402


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "quantile_prediction_runs",
            "quantile_prediction_outputs",
            "quantile_evaluation_reports",
            "analytics_prediction_quantile_evaluation",
        ]
        for name in required:
            row = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (name,)).fetchone()
            if not row or int(row[0]) == 0:
                raise RuntimeError(f"Missing SQLite object: {name}")
        target_ids = {str(row[0]) for row in con.execute("SELECT DISTINCT target_id FROM quantile_prediction_runs")}
        for spec in TARGET_SPECS:
            if spec.target_id not in target_ids:
                raise RuntimeError(f"No quantile runs for target_id={spec.target_id}")
        runs = int(con.execute("SELECT COUNT(*) FROM quantile_prediction_runs").fetchone()[0])
        outputs = int(con.execute("SELECT COUNT(*) FROM quantile_prediction_outputs").fetchone()[0])
        print("prediction quantile validation ok")
        print(f"runs={runs}")
        print(f"outputs={outputs}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
