from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPLAY_DB = PROJECT_ROOT / "deliverables" / "replay_team_metrics_ewc2026_probe6.sqlite"
DEFAULT_MANIFEST = PROJECT_ROOT / "deliverables" / "opendota_replay_manifest_ewc2026_complete157.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "deliverables" / "replay_backfill_status_2026-08-11.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a short replay-backfill coverage report.")
    parser.add_argument("--replay-db", default=str(DEFAULT_REPLAY_DB))
    parser.add_argument("--manifest-json", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--source-name", default="source2_demo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    replay_db = Path(args.replay_db)
    manifest_json = Path(args.manifest_json)
    output_md = Path(args.output_md)

    manifest_rows = json.loads(manifest_json.read_text(encoding="utf-8"))
    total_matches = len(manifest_rows)
    replay_url_matches = sum(1 for row in manifest_rows if row.get("replay_url"))

    con = sqlite3.connect(str(replay_db))
    try:
        distinct_final_matches = con.execute(
            "SELECT COUNT(DISTINCT match_id) FROM replay_team_metric_final WHERE source_name = ?",
            (args.source_name,),
        ).fetchone()[0]
        distinct_event_matches = con.execute(
            "SELECT COUNT(DISTINCT match_id) FROM replay_team_metric_events WHERE source_name = ?",
            (args.source_name,),
        ).fetchone()[0]
        stat_rows = con.execute(
            """
            SELECT stat_name, COUNT(*) AS row_count,
                   SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
                   MIN(raw_value) AS min_raw_value,
                   MAX(raw_value) AS max_raw_value
            FROM replay_team_metric_final
            WHERE source_name = ?
            GROUP BY stat_name
            ORDER BY stat_name
            """,
            (args.source_name,),
        ).fetchall()
    finally:
        con.close()

    markdown = "\n".join(
        [
            "# Replay backfill status",
            "",
            "Date: `2026-08-11`",
            "",
            f"- Tournament matches in manifest: `{total_matches}`",
            f"- Matches with replay URL: `{replay_url_matches}`",
            f"- Matches loaded into `replay_team_metric_final`: `{distinct_final_matches}`",
            f"- Matches loaded into `replay_team_metric_events`: `{distinct_event_matches}`",
            "",
            "## Metric summary",
            "",
            "| stat_name | row_count | nonzero_rows | min_raw_value | max_raw_value |",
            "| --- | ---: | ---: | ---: | ---: |",
            *[
                f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |"
                for row in stat_rows
            ],
            "",
            "## Where to look",
            "",
            "- `replay_team_metric_events` - event-level replay counter updates.",
            "- `replay_team_metric_final` - final values per `match_id + team_side + team_slot + stat_name`.",
            "- `analytics_replay_team_metrics_long` - public long-format replay view.",
            "- `analytics_replay_team_metrics_wide` - one row per team-slot with replay metrics as columns.",
            "- `analytics_replay_match_coverage` - per-match replay coverage summary.",
            "- `analytics_replay_metric_summary` - per-metric coverage summary.",
        ]
    )
    output_md.write_text(markdown + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output_md": str(output_md),
                "total_matches": total_matches,
                "replay_url_matches": replay_url_matches,
                "distinct_final_matches": distinct_final_matches,
                "distinct_event_matches": distinct_event_matches,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
