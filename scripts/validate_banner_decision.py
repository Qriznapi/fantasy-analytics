from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_banner_decision import DB_PATH  # noqa: E402


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        required = [
            "banner_decision_runs",
            "banner_decision_entity_scores",
            "banner_decision_lineups",
            "analytics_banner_decision_players",
            "analytics_banner_decision_role_slots",
            "analytics_banner_decision_lineups",
        ]
        for name in required:
            row = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (name,)).fetchone()
            if not row or int(row[0]) == 0:
                raise RuntimeError(f"Missing SQLite object: {name}")
        runs = int(con.execute("SELECT COUNT(*) FROM banner_decision_runs").fetchone()[0])
        rows = int(con.execute("SELECT COUNT(*) FROM banner_decision_entity_scores").fetchone()[0])
        lineups = int(con.execute("SELECT COUNT(*) FROM banner_decision_lineups").fetchone()[0])
        if runs <= 0 or rows <= 0:
            raise RuntimeError("Banner decision layer is empty.")
        print("banner decision validation ok")
        print(f"runs={runs}")
        print(f"entity_rows={rows}")
        print(f"lineup_rows={lineups}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
