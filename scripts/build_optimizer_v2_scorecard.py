from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "optimizer_v2_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "OPTIMIZER_V2_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        summary_players = pd.read_sql_query(
            """
            SELECT entity_type, role_group, optimizer_scope,
                   COUNT(*) AS rows_scored,
                   AVG(optimizer_v2_score_1_100) AS avg_score
            FROM analytics_optimizer_v2_players
            GROUP BY entity_type, role_group, optimizer_scope
            ORDER BY entity_type, optimizer_scope, role_group
            """,
            con,
        )
        summary_slots = pd.read_sql_query(
            """
            SELECT entity_type, role_slot, optimizer_scope,
                   COUNT(*) AS rows_scored,
                   AVG(optimizer_v2_score_1_100) AS avg_score
            FROM analytics_optimizer_v2_role_slots
            GROUP BY entity_type, role_slot, optimizer_scope
            ORDER BY entity_type, optimizer_scope, role_slot
            """,
            con,
        )
        evaluation = pd.read_sql_query(
            """
            SELECT
                run_id,
                entity_type,
                optimizer_scope,
                MAX(CASE WHEN metric_name = 'mae' THEN metric_value END) AS mae,
                MAX(CASE WHEN metric_name = 'spearman' THEN metric_value END) AS spearman,
                MAX(CASE WHEN metric_name = 'top5_overlap' THEN metric_value END) AS top5_overlap,
                MAX(CASE WHEN metric_name = 'ndcg_5' THEN metric_value END) AS ndcg_5,
                MAX(CASE WHEN metric_name = 'regret_at_1' THEN metric_value END) AS regret_at_1
            FROM analytics_optimizer_v2_evaluation
            GROUP BY run_id, entity_type, optimizer_scope
            ORDER BY entity_type, optimizer_scope
            """,
            con,
        )
        top_players = pd.read_sql_query(
            """
            SELECT optimizer_scope, role_group, official_name, team_name,
                   optimizer_v2_score_1_100, optimizer_v2_raw_score, series_top1_p75, series_mean_p75
            FROM analytics_optimizer_v2_players
            ORDER BY optimizer_scope, role_group, optimizer_v2_score_1_100 DESC, optimizer_v2_raw_score DESC
            """,
            con,
        )
        top_slots = pd.read_sql_query(
            """
            SELECT optimizer_scope, role_slot, player_names, team_name,
                   optimizer_v2_score_1_100, optimizer_v2_raw_score, series_top1_p75, series_mean_p75
            FROM analytics_optimizer_v2_role_slots
            ORDER BY optimizer_scope, role_slot, optimizer_v2_score_1_100 DESC, optimizer_v2_raw_score DESC
            """,
            con,
        )
    finally:
        con.close()

    summary = pd.concat([summary_players, summary_slots], ignore_index=True, sort=False)
    lines: list[str] = []
    lines.append("# Optimizer V2 Scorecard")
    lines.append("")
    lines.append("This scorecard summarizes the stored optimizer-v2 candidate layer.")
    lines.append("")
    lines.append("## Segment Summary")
    lines.append("")
    lines.append("| Entity type | Scope | Segment | Rows | Avg score |")
    lines.append("|---|---|---|---:|---:|")
    for _, row in summary.iterrows():
        segment = row["role_group"] if pd.notna(row["role_group"]) else row["role_slot"]
        lines.append(f"| {row['entity_type']} | {row['optimizer_scope']} | {segment} | {int(row['rows_scored'])} | {row['avg_score']:.2f} |")
    lines.append("")
    lines.append("## Backtest Summary")
    lines.append("")
    lines.append("| Entity type | Scope | MAE | Spearman | Top5 overlap | NDCG@5 | Regret@1 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for _, row in evaluation.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['optimizer_scope']} | {row['mae']:.2f} | {row['spearman']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} |"
        )
    lines.append("")
    for (scope, role_group), block in top_players.groupby(["optimizer_scope", "role_group"], sort=False):
        lines.append(f"## Top Players / {scope} / {role_group}")
        lines.append("")
        lines.append("| Player | Team | Score | Raw | Top1 p75 | Series mean p75 |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for _, row in block.head(8).iterrows():
            lines.append(
                f"| {row['official_name']} | {row['team_name']} | {row['optimizer_v2_score_1_100']:.2f} | {row['optimizer_v2_raw_score']:.2f} | {row['series_top1_p75']:.2f} | {row['series_mean_p75']:.2f} |"
            )
        lines.append("")
    for (scope, role_slot), block in top_slots.groupby(["optimizer_scope", "role_slot"], sort=False):
        lines.append(f"## Top Role Slots / {scope} / {role_slot}")
        lines.append("")
        lines.append("| Players | Team | Score | Raw | Top1 p75 | Series mean p75 |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for _, row in block.head(8).iterrows():
            lines.append(
                f"| {row['player_names']} | {row['team_name']} | {row['optimizer_v2_score_1_100']:.2f} | {row['optimizer_v2_raw_score']:.2f} | {row['series_top1_p75']:.2f} | {row['series_mean_p75']:.2f} |"
            )
        lines.append("")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
