from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "unified_evaluation_runs",
            "unified_evaluation_metrics",
            "analytics_unified_evaluation_metrics",
            "analytics_unified_evaluation_summary",
            "analytics_unified_evaluation_leaderboard",
        ]
        for name in required:
            row = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (name,)).fetchone()
            if not row or int(row[0]) == 0:
                raise RuntimeError(f"Missing SQLite object: {name}")
        runs = int(con.execute("SELECT COUNT(*) FROM unified_evaluation_runs").fetchone()[0])
        metrics = int(con.execute("SELECT COUNT(*) FROM unified_evaluation_metrics").fetchone()[0])
        comparable = int(
            con.execute("SELECT COUNT(*) FROM unified_evaluation_runs WHERE comparable_flag = 1").fetchone()[0]
        )
        if runs <= 0 or metrics <= 0 or comparable <= 0:
            raise RuntimeError("Unified evaluation layer is empty or lacks comparable runs.")
        print("unified evaluation validation ok")
        print(f"runs={runs}")
        print(f"metrics={metrics}")
        print(f"comparable_runs={comparable}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
