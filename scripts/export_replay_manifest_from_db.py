from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tournament_config import load_tournament_config, resolve_event_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export replay manifest rows from cached raw OpenDota payloads stored in the "
            "compact SQLite database."
        )
    )
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--match-limit", type=int, default=0)
    parser.add_argument("--only-missing-local", action="store_true")
    parser.add_argument(
        "--replay-dir",
        default="",
        help="Used with --only-missing-local to skip rows whose .dem.bz2 already exists locally.",
    )
    return parser.parse_args()


def export_manifest_rows(
    db_path: Path,
    *,
    replay_dir: Path | None = None,
    only_missing_local: bool = False,
    match_limit: int = 0,
) -> list[dict[str, object]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT
                rsp.match_id,
                rsp.payload_json,
                m.radiant_name,
                m.dire_name,
                m.series_id,
                m.match_date
            FROM raw_match_source_payloads AS rsp
            LEFT JOIN matches AS m
              ON m.match_id = rsp.match_id
            WHERE rsp.source_name = 'opendota'
            ORDER BY COALESCE(m.match_date, ''), rsp.match_id
            """
        ).fetchall()
    finally:
        con.close()

    manifest: list[dict[str, object]] = []
    for row in rows:
        payload = json.loads(str(row["payload_json"]))
        replay_url = payload.get("replay_url")
        if not replay_url:
            continue
        match_id = int(row["match_id"])
        if only_missing_local and replay_dir is not None:
            local_path = replay_dir / f"{match_id}.dem.bz2"
            if local_path.exists() and local_path.stat().st_size > 0:
                continue
        manifest.append(
            {
                "match_id": match_id,
                "source_name": "opendota_cached_db",
                "status": "ok",
                "cluster": payload.get("cluster"),
                "league_id": payload.get("leagueid"),
                "series_id": payload.get("series_id") or row["series_id"],
                "start_time": payload.get("start_time"),
                "match_date": row["match_date"],
                "radiant_name": payload.get("radiant_name") or row["radiant_name"],
                "dire_name": payload.get("dire_name") or row["dire_name"],
                "replay_salt": payload.get("replay_salt"),
                "replay_url": replay_url,
                "has_players": bool(payload.get("players")),
                "players_count": len(payload.get("players") or []),
                "source_db": str(db_path),
            }
        )
        if match_limit > 0 and len(manifest) >= match_limit:
            break
    return manifest


def main() -> int:
    args = parse_args()
    config = load_tournament_config(args.event_id)
    db_path = Path(args.db_path) if args.db_path else resolve_event_db_path(args.event_id)
    replay_dir = Path(args.replay_dir) if args.replay_dir else config.cache_dir / "replays"
    output_json = Path(args.output_json) if args.output_json else config.replay_manifest_path
    output_json.parent.mkdir(parents=True, exist_ok=True)
    if args.only_missing_local:
        replay_dir.mkdir(parents=True, exist_ok=True)

    manifest = export_manifest_rows(
        db_path,
        replay_dir=replay_dir,
        only_missing_local=args.only_missing_local,
        match_limit=args.match_limit,
    )
    output_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "event_id": args.event_id,
                "db_path": str(db_path),
                "output_json": str(output_json),
                "rows_written": len(manifest),
                "replay_dir_checked": str(replay_dir) if args.only_missing_local else None,
                "only_missing_local": bool(args.only_missing_local),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
