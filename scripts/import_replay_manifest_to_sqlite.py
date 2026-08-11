from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


DDL = """
CREATE TABLE IF NOT EXISTS replay_match_manifest (
    match_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    fetched_at_utc TEXT,
    http_status INTEGER,
    content_type TEXT,
    status TEXT NOT NULL,
    error TEXT,
    cluster INTEGER,
    league_id INTEGER,
    series_id INTEGER,
    start_time INTEGER,
    radiant_name TEXT,
    dire_name TEXT,
    replay_salt INTEGER,
    replay_url TEXT,
    has_players INTEGER,
    players_count INTEGER,
    download_probe_http_status INTEGER,
    download_probe_content_length INTEGER,
    download_probe_content_type TEXT,
    download_probe_prefix_ascii TEXT,
    download_probe_prefix_hex TEXT
);
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import replay manifest JSON into SQLite.")
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--sqlite-path", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_json)
    sqlite_path = Path(args.sqlite_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    rows = json.loads(input_path.read_text(encoding="utf-8"))
    con = sqlite3.connect(sqlite_path)
    con.execute(DDL)

    for row in rows:
        probe = row.get("download_probe") or {}
        con.execute(
            """
            INSERT OR REPLACE INTO replay_match_manifest (
                match_id, source_name, fetched_at_utc, http_status, content_type, status, error,
                cluster, league_id, series_id, start_time, radiant_name, dire_name,
                replay_salt, replay_url, has_players, players_count,
                download_probe_http_status, download_probe_content_length,
                download_probe_content_type, download_probe_prefix_ascii, download_probe_prefix_hex
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("match_id"),
                row.get("source_name"),
                row.get("fetched_at_utc"),
                row.get("http_status"),
                row.get("content_type"),
                row.get("status"),
                row.get("error"),
                row.get("cluster"),
                row.get("league_id"),
                row.get("series_id"),
                row.get("start_time"),
                row.get("radiant_name"),
                row.get("dire_name"),
                row.get("replay_salt"),
                row.get("replay_url"),
                int(bool(row.get("has_players"))) if row.get("has_players") is not None else None,
                row.get("players_count"),
                probe.get("http_status"),
                probe.get("content_length"),
                probe.get("content_type"),
                probe.get("prefix_ascii"),
                probe.get("prefix_hex"),
            ),
        )

    con.commit()
    summary = con.execute(
        """
        SELECT
            COUNT(*) AS total_rows,
            SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_rows,
            SUM(CASE WHEN replay_url IS NOT NULL THEN 1 ELSE 0 END) AS replay_url_rows
        FROM replay_match_manifest
        """
    ).fetchone()
    con.close()

    print(
        json.dumps(
            {
                "sqlite_path": str(sqlite_path),
                "total_rows": summary[0],
                "ok_rows": summary[1],
                "replay_url_rows": summary[2],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
