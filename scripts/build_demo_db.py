"""Build a tiny deterministic SQLite database for demos and CI."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "sample" / "demo.sqlite"

ROWS = [
    ("Aster", "Aurora", 1, "core", "creep_score", 1840.0, 2580.0, "Group Stage"),
    ("Aster", "Aurora", 1, "core", "kills", 910.0, 1640.0, "Group Stage"),
    ("Blaze", "Borealis", 2, "mid", "runes_grabbed", 1210.0, 1900.0, "Group Stage"),
    ("Blaze", "Borealis", 2, "mid", "teamfight_participation", 1380.0, 2050.0, "Playoffs"),
    ("Cinder", "Aurora", 4, "support", "wards_placed", 420.0, 790.0, "Playoffs"),
    ("Dawn", "Borealis", 5, "support", "teamfight_participation", 1070.0, 1490.0, "Playoffs"),
]


def build_demo_db(path: Path = DEFAULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE analytics_player_maps (
                official_name TEXT NOT NULL,
                team_name TEXT NOT NULL,
                official_position INTEGER NOT NULL,
                role_group TEXT NOT NULL,
                stat_name TEXT NOT NULL,
                fantasy_score REAL NOT NULL,
                p75_fantasy_score REAL NOT NULL,
                stage_name TEXT NOT NULL
            )
            """
        )
        con.executemany("INSERT INTO analytics_player_maps VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ROWS)
        con.execute(
            """
            CREATE VIEW analytics_demo_leaderboard AS
            SELECT official_name, team_name, role_group,
                   ROUND(AVG(fantasy_score), 2) AS avg_fantasy_points,
                   ROUND(MAX(p75_fantasy_score), 2) AS p75_fantasy_points
            FROM analytics_player_maps
            GROUP BY official_name, team_name, role_group
            ORDER BY p75_fantasy_points DESC
            """
        )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the portable Dota Fantasy demo database.")
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    print(build_demo_db(args.output))


if __name__ == "__main__":
    main()
