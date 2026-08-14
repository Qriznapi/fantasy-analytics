from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "optimizer_foundation_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "OPTIMIZER_FOUNDATION_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        player_summary = pd.read_sql_query(
            """
            SELECT
                entity_type,
                role_group,
                optimizer_scope,
                COUNT(*) AS rows_scored,
                AVG(optimizer_score_1_100) AS avg_optimizer_1_100,
                AVG(expected_estimate) AS avg_expected,
                AVG(high_estimate) AS avg_high,
                AVG(reliability_score_1_100) AS avg_reliability_1_100,
                AVG(stat_balance_score) AS avg_stat_balance,
                AVG(volatility_ratio) AS avg_volatility
            FROM analytics_optimizer_players_foundation
            GROUP BY entity_type, role_group, optimizer_scope
            ORDER BY entity_type, optimizer_scope, role_group
            """,
            con,
        )
        slot_summary = pd.read_sql_query(
            """
            SELECT
                entity_type,
                role_slot,
                optimizer_scope,
                COUNT(*) AS rows_scored,
                AVG(optimizer_score_1_100) AS avg_optimizer_1_100,
                AVG(expected_estimate) AS avg_expected,
                AVG(high_estimate) AS avg_high,
                AVG(reliability_score_1_100) AS avg_reliability_1_100,
                AVG(stat_balance_score) AS avg_stat_balance,
                AVG(volatility_ratio) AS avg_volatility
            FROM analytics_optimizer_role_slots_foundation
            GROUP BY entity_type, role_slot, optimizer_scope
            ORDER BY entity_type, optimizer_scope, role_slot
            """,
            con,
        )
        top_players = pd.read_sql_query(
            """
            SELECT
                optimizer_scope,
                role_group,
                team_name,
                official_name,
                optimizer_score_1_100,
                optimizer_raw_score,
                expected_estimate,
                high_estimate,
                reliability_score_1_100,
                series_top1_p75,
                stat_balance_score
            FROM analytics_optimizer_players_foundation
            ORDER BY optimizer_scope, role_group, optimizer_score_1_100 DESC, expected_estimate DESC
            """,
            con,
        )
        top_slots = pd.read_sql_query(
            """
            SELECT
                optimizer_scope,
                role_slot,
                team_name,
                player_names,
                optimizer_score_1_100,
                optimizer_raw_score,
                expected_estimate,
                high_estimate,
                reliability_score_1_100,
                series_top1_p75,
                stat_balance_score
            FROM analytics_optimizer_role_slots_foundation
            ORDER BY optimizer_scope, role_slot, optimizer_score_1_100 DESC, expected_estimate DESC
            """,
            con,
        )
        evaluation = pd.read_sql_query(
            """
            SELECT
                run_id,
                entity_type,
                optimizer_scope,
                MAX(CASE WHEN metric_name = 'mae' AND metric_scope = 'entity' THEN metric_value END) AS mae,
                MAX(CASE WHEN metric_name = 'spearman' AND metric_scope = 'entity' THEN metric_value END) AS spearman,
                MAX(CASE WHEN metric_name = 'top3_overlap' AND metric_scope = 'entity' THEN metric_value END) AS top3_overlap,
                MAX(CASE WHEN metric_name = 'top5_overlap' AND metric_scope = 'entity' THEN metric_value END) AS top5_overlap,
                MAX(CASE WHEN metric_name = 'ndcg_5' AND metric_scope = 'entity' THEN metric_value END) AS ndcg_5,
                MAX(CASE WHEN metric_name = 'ndcg_10' AND metric_scope = 'entity' THEN metric_value END) AS ndcg_10,
                MAX(CASE WHEN metric_name = 'regret_at_1' AND metric_scope = 'entity' THEN metric_value END) AS regret_at_1
            FROM analytics_optimizer_foundation_evaluation
            GROUP BY run_id, entity_type, optimizer_scope
            ORDER BY entity_type, optimizer_scope
            """,
            con,
        )
        baselines = pd.read_sql_query(
            """
            SELECT
                run_id,
                entity_type,
                optimizer_scope,
                baseline_id,
                MAX(CASE WHEN metric_name = 'mae' AND metric_scope = 'entity' AND segment_key = 'all' THEN metric_value END) AS mae,
                MAX(CASE WHEN metric_name = 'spearman' AND metric_scope = 'entity' AND segment_key = 'all' THEN metric_value END) AS spearman,
                MAX(CASE WHEN metric_name = 'top5_overlap' AND metric_scope = 'entity' AND segment_key = 'all' THEN metric_value END) AS top5_overlap,
                MAX(CASE WHEN metric_name = 'ndcg_5' AND metric_scope = 'entity' AND segment_key = 'all' THEN metric_value END) AS ndcg_5,
                MAX(CASE WHEN metric_name = 'regret_at_1' AND metric_scope = 'entity' AND segment_key = 'all' THEN metric_value END) AS regret_at_1
            FROM analytics_optimizer_foundation_baselines
            GROUP BY run_id, entity_type, optimizer_scope, baseline_id
            ORDER BY entity_type, optimizer_scope, baseline_id
            """,
            con,
        )
        segment_regret = pd.read_sql_query(
            """
            SELECT
                entity_type,
                optimizer_scope,
                baseline_id,
                segment_key,
                MAX(CASE WHEN metric_name = 'regret_at_1' THEN metric_value END) AS regret_at_1,
                MAX(CASE WHEN metric_name = 'spearman' THEN metric_value END) AS spearman
            FROM analytics_optimizer_foundation_baselines
            WHERE metric_scope = 'segment'
            GROUP BY entity_type, optimizer_scope, baseline_id, segment_key
            ORDER BY entity_type, optimizer_scope, segment_key, baseline_id
            """,
            con,
        )
    finally:
        con.close()

    summary = pd.concat([player_summary, slot_summary], ignore_index=True, sort=False)

    lines: list[str] = []
    lines.append("# Optimizer Foundation Scorecard")
    lines.append("")
    lines.append(
        "This scorecard summarizes the newer foundation-first optimizer layer. It is a recommendation surface built on top of the reliability foundation, with extra emphasis on usable ceiling, balanced stat exposure, and lineup-oriented upside."
    )
    lines.append("")

    if summary.empty:
        lines.append("No optimizer foundation rows are available.")
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(lines) + "\n"
        OUT_PATH.write_text(payload, encoding="utf-8")
        DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
        print(str(OUT_PATH))
        return

    lines.append("## Segment Summary")
    lines.append("")
    lines.append("| Entity type | Scope | Segment | Rows | Avg optimizer | Avg expected | Avg high | Avg reliability | Avg stat balance | Avg volatility |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for _, row in summary.iterrows():
        segment = row["role_group"] if pd.notna(row["role_group"]) else row["role_slot"]
        lines.append(
            f"| {row['entity_type']} | {row['optimizer_scope']} | {segment} | {int(row['rows_scored'])} | {row['avg_optimizer_1_100']:.2f} | {row['avg_expected']:.2f} | {row['avg_high']:.2f} | {row['avg_reliability_1_100']:.2f} | {row['avg_stat_balance']:.3f} | {row['avg_volatility']:.3f} |"
        )
    lines.append("")

    lines.append("## Backtest Summary")
    lines.append("")
    lines.append("| Entity type | Scope | MAE | Spearman | Top3 overlap | Top5 overlap | NDCG@5 | NDCG@10 | Regret@1 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for _, row in evaluation.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['optimizer_scope']} | {row['mae']:.2f} | {row['spearman']:.3f} | {row['top3_overlap']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['ndcg_10']:.3f} | {row['regret_at_1']:.2f} |"
        )
    lines.append("")

    lines.append("## Baseline Comparison")
    lines.append("")
    lines.append("| Entity type | Scope | Baseline | MAE | Spearman | Top5 overlap | NDCG@5 | Regret@1 |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    for _, row in baselines.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['optimizer_scope']} | {row['baseline_id']} | {row['mae']:.2f} | {row['spearman']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} |"
        )
    lines.append("")

    lines.append("## Segment Regret vs Baselines")
    lines.append("")
    lines.append("| Entity type | Scope | Segment | Baseline | Regret@1 | Spearman |")
    lines.append("|---|---|---|---|---:|---:|")
    for _, row in segment_regret.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['optimizer_scope']} | {row['segment_key']} | {row['baseline_id']} | {row['regret_at_1']:.2f} | {row['spearman']:.3f} |"
        )
    lines.append("")

    for (scope, role_group), block in top_players.groupby(["optimizer_scope", "role_group"], sort=False):
        lines.append(f"## Top Players / {scope} / {role_group}")
        lines.append("")
        lines.append("| Player | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in block.head(8).iterrows():
            lines.append(
                f"| {row['official_name']} | {row['team_name']} | {row['optimizer_score_1_100']:.2f} | {row['optimizer_raw_score']:.2f} | {row['expected_estimate']:.2f} | {row['high_estimate']:.2f} | {row['reliability_score_1_100']:.2f} | {row['series_top1_p75']:.2f} | {row['stat_balance_score']:.3f} |"
            )
        lines.append("")

    for (scope, role_slot), block in top_slots.groupby(["optimizer_scope", "role_slot"], sort=False):
        lines.append(f"## Top Role Slots / {scope} / {role_slot}")
        lines.append("")
        lines.append("| Players | Team | Optimizer | Raw | Expected | High | Reliability | Top1 p75 | Stat balance |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in block.head(8).iterrows():
            lines.append(
                f"| {row['player_names']} | {row['team_name']} | {row['optimizer_score_1_100']:.2f} | {row['optimizer_raw_score']:.2f} | {row['expected_estimate']:.2f} | {row['high_estimate']:.2f} | {row['reliability_score_1_100']:.2f} | {row['series_top1_p75']:.2f} | {row['stat_balance_score']:.3f} |"
            )
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
