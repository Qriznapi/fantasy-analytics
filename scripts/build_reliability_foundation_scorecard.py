from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "reliability_foundation_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "RELIABILITY_FOUNDATION_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        summary = pd.read_sql_query(
            """
            SELECT
                s.entity_type,
                s.role_group,
                s.role_slot,
                COUNT(*) AS rows_scored,
                AVG(s.reliability_score_1_100) AS avg_reliability_1_100,
                AVG(s.expected_estimate) AS avg_expected,
                AVG(s.high_estimate - s.low_estimate) AS avg_band_width,
                AVG(CASE s.confidence_label WHEN 'high' THEN 1.0 WHEN 'medium' THEN 0.5 ELSE 0.0 END) AS confidence_index
            FROM foundation_reliability_entity_scores s
            GROUP BY s.entity_type, s.role_group, s.role_slot
            ORDER BY s.entity_type, s.role_group, s.role_slot
            """,
            con,
        )
        backtest = pd.read_sql_query(
            """
            SELECT
                r.entity_type,
                b.segment_key,
                COUNT(*) AS rows_backtested,
                AVG(b.abs_error) AS mae,
                MIN(b.actual_test_score) AS min_actual,
                MAX(b.actual_test_score) AS max_actual
            FROM foundation_reliability_backtest b
            JOIN foundation_reliability_runs r
              ON r.run_id = b.run_id
            GROUP BY r.entity_type, b.segment_key
            ORDER BY r.entity_type, b.segment_key
            """,
            con,
        )
        top_players = pd.read_sql_query(
            """
            SELECT
                role_group,
                team_name,
                official_name,
                reliability_score_1_100,
                expected_estimate,
                low_estimate,
                high_estimate,
                confidence_label
            FROM analytics_reliable_players_foundation
            WHERE ti2026_qualified = 1
            ORDER BY role_group, reliability_score_1_100 DESC, expected_estimate DESC
            """,
            con,
        )
        top_slots = pd.read_sql_query(
            """
            SELECT
                role_slot,
                team_name,
                player_names,
                reliability_score_1_100,
                expected_estimate,
                low_estimate,
                high_estimate,
                confidence_label
            FROM analytics_reliable_role_slots_foundation
            WHERE ti2026_qualified = 1
            ORDER BY role_slot, reliability_score_1_100 DESC, expected_estimate DESC
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Reliability Foundation Scorecard")
    lines.append("")
    lines.append(
        "This scorecard summarizes the new foundation-first reliability layer. It uses group-stage data as the training side and non-group-stage data as the playoff-style backtest surface."
    )
    lines.append("")

    if summary.empty:
        lines.append("No reliability foundation rows are available.")
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(lines) + "\n"
        OUT_PATH.write_text(payload, encoding="utf-8")
        DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
        print(str(OUT_PATH))
        return

    lines.append("## Segment Summary")
    lines.append("")
    lines.append("| Entity type | Segment | Rows | Avg reliability | Avg expected | Avg band width | Confidence index |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for _, row in summary.iterrows():
        segment = row["role_group"] if pd.notna(row["role_group"]) else row["role_slot"]
        lines.append(
            f"| {row['entity_type']} | {segment} | {int(row['rows_scored'])} | {row['avg_reliability_1_100']:.2f} | {row['avg_expected']:.2f} | {row['avg_band_width']:.2f} | {row['confidence_index']:.2f} |"
        )
    lines.append("")

    lines.append("## Backtest Summary")
    lines.append("")
    lines.append("| Entity type | Segment | Rows backtested | MAE | Min actual | Max actual |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for _, row in backtest.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['segment_key']} | {int(row['rows_backtested'])} | {row['mae']:.2f} | {row['min_actual']:.2f} | {row['max_actual']:.2f} |"
        )
    lines.append("")

    for role_group, block in top_players.groupby("role_group", sort=False):
        lines.append(f"## Top Players / {role_group}")
        lines.append("")
        lines.append("| Player | Team | Reliability | Expected | Low | High | Confidence |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for _, row in block.head(8).iterrows():
            lines.append(
                f"| {row['official_name']} | {row['team_name']} | {row['reliability_score_1_100']:.2f} | {row['expected_estimate']:.2f} | {row['low_estimate']:.2f} | {row['high_estimate']:.2f} | {row['confidence_label']} |"
            )
        lines.append("")

    for role_slot, block in top_slots.groupby("role_slot", sort=False):
        lines.append(f"## Top Role Slots / {role_slot}")
        lines.append("")
        lines.append("| Players | Team | Reliability | Expected | Low | High | Confidence |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for _, row in block.head(8).iterrows():
            lines.append(
                f"| {row['player_names']} | {row['team_name']} | {row['reliability_score_1_100']:.2f} | {row['expected_estimate']:.2f} | {row['low_estimate']:.2f} | {row['high_estimate']:.2f} | {row['confidence_label']} |"
            )
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
