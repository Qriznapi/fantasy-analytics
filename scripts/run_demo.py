"""Run a portable analytics demo without local tournament artifacts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from build_demo_db import DEFAULT_PATH, build_demo_db


def main() -> None:
    path = build_demo_db(DEFAULT_PATH)
    with sqlite3.connect(path) as con:
        rows = con.execute("SELECT * FROM analytics_demo_leaderboard").fetchall()
    print("Dota Fantasy Analytics demo")
    print("official_name | team_name | role_group | avg_fantasy_points | p75_fantasy_points")
    for row in rows:
        print(" | ".join(map(str, row)))
    print(f"\nDemo database: {path}")


if __name__ == "__main__":
    main()
