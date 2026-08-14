from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_production_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_PRODUCTION_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        choices = pd.read_sql_query(
            """
            SELECT *
            FROM analytics_prediction_production_model_choices
            ORDER BY target_id, split_name
            """,
            con,
        )
        top_players = pd.read_sql_query(
            """
            SELECT split_name, target_id, chosen_family, chosen_model_id,
                   official_name, team_name, official_position, role_group,
                   predicted_score, q75, metric_entity_spearman, metric_ndcg_5
            FROM analytics_prediction_production_players
            ORDER BY split_name, target_id, predicted_score DESC
            """,
            con,
        )
        top_slots = pd.read_sql_query(
            """
            SELECT split_name, target_id, chosen_family, chosen_model_id,
                   player_names, team_name, role_slot,
                   predicted_score, q75, metric_entity_spearman, metric_ndcg_5
            FROM analytics_prediction_production_role_slots
            ORDER BY split_name, target_id, predicted_score DESC
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Prediction Production Scorecard")
    lines.append("")
    lines.append("This scorecard summarizes the production prediction surface. It does not assume a single global model; instead, it stores the historically strongest model choice per target/split and then recomputes current entity scores on the full available dataset.")
    lines.append("")
    if choices.empty:
        lines.append("No production prediction choices are available.")
    else:
        lines.append("## Chosen Model Per Target")
        lines.append("")
        lines.append("| Target | Split | Family | Model | Param A | Param B | Entity sp. | NDCG@5 | Top5 overlap | MAE | Regret@1 |")
        lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in choices.iterrows():
            pa = "" if pd.isna(row["param_a"]) else f"{float(row['param_a']):.2f}"
            pb = "" if pd.isna(row["param_b"]) else f"{float(row['param_b']):.3f}"
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {row['chosen_family']} | {row['chosen_model_id']} | {pa} | {pb} | {row['metric_entity_spearman']:.3f} | {row['metric_ndcg_5']:.3f} | {row['metric_top5_overlap']:.3f} | {row['metric_mae']:.2f} | {row['metric_regret_at_1']:.2f} |"
            )
        lines.append("")

    for (split_name, target_id), block in top_players.groupby(["split_name", "target_id"], sort=False):
        lines.append(f"## Top Players / {split_name} / {target_id}")
        lines.append("")
        lines.append("| Player | Team | Pos | Role | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |")
        lines.append("|---|---|---:|---|---:|---:|---|---:|---:|")
        for _, row in block.head(10).iterrows():
            q75 = "" if pd.isna(row["q75"]) else f"{float(row['q75']):.2f}"
            lines.append(
                f"| {row['official_name']} | {row['team_name']} | {int(row['official_position']) if pd.notna(row['official_position']) else ''} | {row['role_group']} | {row['predicted_score']:.2f} | {q75} | {row['chosen_family']} | {row['metric_entity_spearman']:.3f} | {row['metric_ndcg_5']:.3f} |"
            )
        lines.append("")

    for (split_name, target_id), block in top_slots.groupby(["split_name", "target_id"], sort=False):
        lines.append(f"## Top Role Slots / {split_name} / {target_id}")
        lines.append("")
        lines.append("| Players | Team | Role slot | Score | Q75 | Model family | Eval sp. | Eval NDCG@5 |")
        lines.append("|---|---|---|---:|---:|---|---:|---:|")
        for _, row in block.head(10).iterrows():
            q75 = "" if pd.isna(row["q75"]) else f"{float(row['q75']):.2f}"
            lines.append(
                f"| {row['player_names']} | {row['team_name']} | {row['role_slot']} | {row['predicted_score']:.2f} | {q75} | {row['chosen_family']} | {row['metric_entity_spearman']:.3f} | {row['metric_ndcg_5']:.3f} |"
            )
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
