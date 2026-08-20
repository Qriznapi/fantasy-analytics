import sqlite3

from build_demo_db import build_demo_db


def test_demo_database_has_a_queryable_leaderboard(tmp_path):
    path = build_demo_db(tmp_path / "demo.sqlite")
    with sqlite3.connect(path) as con:
        rows = con.execute("SELECT * FROM analytics_demo_leaderboard").fetchall()
    assert len(rows) == 4
    assert rows[0][0] == "Aster"
