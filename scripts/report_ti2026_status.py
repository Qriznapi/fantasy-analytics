from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from tournament_config import resolve_event_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact status report for the TI 2026 live database.")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--write-markdown", action="store_true")
    parser.add_argument("--markdown-path", default="")
    return parser.parse_args()


def build_status(db_path: Path) -> dict[str, object]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        counts = {
            table_name: int(con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
            for table_name in [
                "matches",
                "player_match_stats",
                "team_match_stats",
                "player_game_fantasy_summary",
                "fantasy_player_map_stat_points",
                "raw_match_source_payloads",
                "stg_player_match_enriched_stats",
                "player_identity_registry",
                "liquipedia_team_rosters",
                "ti_qualified_teams",
                "event_sync_runs",
                "event_sync_match_log",
            ]
        }
        latest_sync = con.execute(
            """
            SELECT run_id, status, started_at_utc, finished_at_utc,
                   new_match_count, updated_match_count, failed_match_count, notes
            FROM event_sync_runs
            WHERE event_id = 'ti2026'
            ORDER BY started_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        stage_buckets = [dict(row) for row in con.execute(
            "SELECT stage_bucket, is_group_stage_bucket, is_main_playoff, COUNT(*) AS maps FROM matches GROUP BY stage_bucket, is_group_stage_bucket, is_main_playoff ORDER BY stage_bucket"
        ).fetchall()]
        identity_confidence = [dict(row) for row in con.execute(
            "SELECT confidence_label, COUNT(*) AS rows FROM player_identity_registry GROUP BY confidence_label ORDER BY rows DESC"
        ).fetchall()]
        backfill_coverage = [dict(row) for row in con.execute(
            """
            SELECT stat_name, coverage_status, final_rows, nonzero_raw_rows, zero_raw_rows,
                   has_stage_evidence, is_row_complete
            FROM analytics_fantasy_backfill_coverage
            ORDER BY stat_name
            """
        ).fetchall()]
        top_maps = [dict(row) for row in con.execute(
            """
            SELECT official_name, team_name, official_position, hero_name, fantasy_score, match_date
            FROM analytics_player_maps
            WHERE ti2026_qualified = 1
            ORDER BY fantasy_score DESC
            LIMIT 10
            """
        ).fetchall()]
        return {
            "db_path": str(db_path),
            "counts": counts,
            "latest_sync": dict(latest_sync) if latest_sync else None,
            "stage_buckets": stage_buckets,
            "identity_confidence": identity_confidence,
            "backfill_coverage": backfill_coverage,
            "top_maps": top_maps,
        }
    finally:
        con.close()


def render_markdown(status: dict[str, object]) -> str:
    latest_sync = status.get("latest_sync") or {}
    lines = [
        "# TI 2026 Live Status",
        "",
        f"- Database: `{status['db_path']}`",
        f"- Matches: **{status['counts']['matches']}**",
        f"- Player-map rows: **{status['counts']['player_game_fantasy_summary']}**",
        f"- Raw payloads: **{status['counts']['raw_match_source_payloads']}**",
        f"- Latest sync run: `{latest_sync.get('run_id', '-')}`",
        f"- Latest sync status: **{latest_sync.get('status', '-')}**",
        f"- New matches in latest sync: **{latest_sync.get('new_match_count', 0)}**",
        f"- Updated matches in latest sync: **{latest_sync.get('updated_match_count', 0)}**",
        f"- Failed matches in latest sync: **{latest_sync.get('failed_match_count', 0)}**",
        "",
        "## Stage buckets",
        "",
        "| stage_bucket | group_bucket | main_playoff | maps |",
        "|---|---:|---:|---:|",
    ]
    for row in status["stage_buckets"]:
        lines.append(f"| {row['stage_bucket']} | {row['is_group_stage_bucket']} | {row['is_main_playoff']} | {row['maps']} |")
    lines.extend([
        "",
        "## Identity confidence",
        "",
        "| confidence_label | rows |",
        "|---|---:|",
    ])
    for row in status["identity_confidence"]:
        lines.append(f"| {row['confidence_label']} | {row['rows']} |")
    lines.extend([
        "",
        "## Backfill coverage",
        "",
        "| stat_name | coverage_status | final_rows | nonzero_raw_rows | zero_raw_rows | has_stage_evidence | is_row_complete |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in status["backfill_coverage"]:
        lines.append(
            f"| {row['stat_name']} | {row['coverage_status']} | {row['final_rows']} | {row['nonzero_raw_rows']} | {row['zero_raw_rows']} | {row['has_stage_evidence']} | {row['is_row_complete']} |"
        )
    lines.extend([
        "",
        "## Top fantasy maps",
        "",
        "| official_name | team_name | pos | hero_name | fantasy_score | match_date |",
        "|---|---|---:|---|---:|---|",
    ])
    for row in status["top_maps"]:
        lines.append(
            f"| {row['official_name']} | {row['team_name']} | {row['official_position']} | {row['hero_name']} | {row['fantasy_score']:.2f} | {row['match_date']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path) if args.db_path else resolve_event_db_path("ti2026")
    status = build_status(db_path)
    if args.write_markdown:
        markdown_path = Path(args.markdown_path) if args.markdown_path else PROJECT_ROOT / "reports" / "ti2026_status.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(status), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
