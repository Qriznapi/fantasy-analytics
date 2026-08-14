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
            "production_prediction_model_choices",
            "production_prediction_entity_scores",
            "analytics_prediction_production_model_choices",
            "analytics_prediction_production_players",
            "analytics_prediction_production_role_slots",
        ]
        for name in required:
            row = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (name,)).fetchone()
            if not row or int(row[0]) == 0:
                raise RuntimeError(f"Missing SQLite object: {name}")
        choices = int(con.execute("SELECT COUNT(*) FROM production_prediction_model_choices").fetchone()[0])
        scores = int(con.execute("SELECT COUNT(*) FROM production_prediction_entity_scores").fetchone()[0])
        print("prediction production validation ok")
        print(f"choices={choices}")
        print(f"scores={scores}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
