from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_monte_carlo_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_MONTE_CARLO_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        summary = pd.read_sql_query(
            """
            SELECT target_id, split_name, entity_type, segment_key,
                   COUNT(*) AS entities,
                   AVG(p_top1) AS avg_p_top1,
                   AVG(p_top3) AS avg_p_top3,
                   AVG(simulated_std_score) AS avg_sim_std
            FROM production_monte_carlo_entity_results
            GROUP BY target_id, split_name, entity_type, segment_key
            ORDER BY target_id, split_name, entity_type, segment_key
            """,
            con,
        )
        top_players = pd.read_sql_query(
            """
            SELECT target_id, split_name, team_name, official_name, official_position, role_group,
                   predicted_score, p_top1, p_top3, p_top5, expected_rank, simulated_std_score
            FROM analytics_prediction_monte_carlo_players
            WHERE ti2026_qualified = 1
            ORDER BY target_id, split_name, p_top1 DESC, p_top3 DESC, predicted_score DESC
            """,
            con,
        )
        top_slots = pd.read_sql_query(
            """
            SELECT target_id, split_name, team_name, player_names, role_slot,
                   predicted_score, p_top1, p_top3, p_top5, expected_rank, simulated_std_score
            FROM analytics_prediction_monte_carlo_role_slots
            WHERE ti2026_qualified = 1
            ORDER BY target_id, split_name, p_top1 DESC, p_top3 DESC, predicted_score DESC
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Prediction Monte Carlo Scorecard")
    lines.append("")
    lines.append("This scorecard summarizes the Monte Carlo layer built on top of the production prediction surface. It estimates ranking stability and upside probabilities by repeatedly sampling entity scores from the stored predictive surface plus uncertainty scale.")
    lines.append("")
    if summary.empty:
        lines.append("No Monte Carlo rows are available.")
    else:
        lines.append("| Target | Split | Entity type | Segment | Entities | Avg p_top1 | Avg p_top3 | Avg sim std |")
        lines.append("|---|---|---|---|---:|---:|---:|---:|")
        for _, row in summary.iterrows():
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {row['entity_type']} | {row['segment_key']} | {int(row['entities'])} | {row['avg_p_top1']:.3f} | {row['avg_p_top3']:.3f} | {row['avg_sim_std']:.2f} |"
            )
        lines.append("")

    for (target_id, split_name), block in top_players.groupby(["target_id", "split_name"], sort=False):
        lines.append(f"## Top Players / {target_id} / {split_name}")
        lines.append("")
        lines.append("| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |")
        lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|")
        for _, row in block.head(10).iterrows():
            lines.append(
                f"| {row['official_name']} | {row['team_name']} | {int(row['official_position']) if pd.notna(row['official_position']) else ''} | {row['role_group']} | {row['predicted_score']:.2f} | {row['p_top1']:.3f} | {row['p_top3']:.3f} | {row['p_top5']:.3f} | {row['expected_rank']:.2f} | {row['simulated_std_score']:.2f} |"
            )
        lines.append("")

    for (target_id, split_name), block in top_slots.groupby(["target_id", "split_name"], sort=False):
        lines.append(f"## Top Role Slots / {target_id} / {split_name}")
        lines.append("")
        lines.append("| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
        for _, row in block.head(10).iterrows():
            lines.append(
                f"| {row['player_names']} | {row['team_name']} | {row['role_slot']} | {row['predicted_score']:.2f} | {row['p_top1']:.3f} | {row['p_top3']:.3f} | {row['p_top5']:.3f} | {row['expected_rank']:.2f} | {row['simulated_std_score']:.2f} |"
            )
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
