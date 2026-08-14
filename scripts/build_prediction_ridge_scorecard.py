from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_ridge_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_RIDGE_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        ridge = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                r.model_id,
                r.alpha,
                r.tuned_on_split,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'spearman' AND e.metric_scope = 'row' THEN e.metric_value END) AS spearman_row,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM ridge_prediction_runs r
            JOIN ridge_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name, r.model_id, r.alpha, r.tuned_on_split
            ORDER BY r.target_id, r.split_name
            """,
            con,
        )
        tuning = pd.read_sql_query(
            """
            SELECT
                target_id,
                split_name,
                alpha,
                MAX(CASE WHEN metric_name = 'entity_spearman' THEN metric_value END) AS entity_spearman,
                MAX(CASE WHEN metric_name = 'ndcg_5' THEN metric_value END) AS ndcg_5,
                MAX(CASE WHEN metric_name = 'mae' THEN metric_value END) AS mae
            FROM analytics_prediction_ridge_tuning
            GROUP BY target_id, split_name, alpha
            ORDER BY target_id, split_name, entity_spearman DESC, ndcg_5 DESC, mae ASC
            """,
            con,
        )
        baseline_best = pd.read_sql_query(
            """
            WITH ranked AS (
                SELECT
                    r.target_id,
                    r.split_name,
                    r.model_id,
                    MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                    MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                    MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                    MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
                    MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
                FROM foundation_prediction_runs r
                JOIN foundation_evaluation_reports e
                  ON e.run_id = r.run_id
                GROUP BY r.target_id, r.split_name, r.model_id
            )
            SELECT *
            FROM ranked
            ORDER BY target_id, split_name, spearman_entity DESC, ndcg_5 DESC, mae ASC
            """,
            con,
        )
        best_rows = (
            baseline_best.groupby(["target_id", "split_name"], as_index=False, sort=False)
            .head(1)
            .reset_index(drop=True)
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Prediction Ridge Scorecard")
    lines.append("")
    lines.append("This scorecard tracks the tuned ridge layer on top of the shared richer feature foundation. Ridge v2 uses a wider feature family plus inner-train alpha selection, then compares the final runs against the best current baseline per target/split.")
    lines.append("")

    if ridge.empty:
        lines.append("No ridge evaluation rows are available.")
    else:
        lines.append("## Ridge Results")
        lines.append("")
        lines.append("| Target | Split | Alpha | Tuning split | MAE | Spearman row | Spearman entity | Top5 overlap | NDCG@5 | Regret@1 |")
        lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|")
        for _, row in ridge.iterrows():
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {row['alpha']:.2f} | {row['tuned_on_split']} | {row['mae']:.2f} | {row['spearman_row']:.3f} | {row['spearman_entity']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} |"
            )
        lines.append("")
    if not tuning.empty:
        lines.append("## Tuning Snapshot")
        lines.append("")
        lines.append("| Target | Split | Alpha | Inner entity sp. | Inner NDCG@5 | Inner MAE |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for _, row in tuning.groupby(["target_id", "split_name"], sort=False).head(3).iterrows():
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {row['alpha']:.2f} | {row['entity_spearman']:.3f} | {row['ndcg_5']:.3f} | {row['mae']:.2f} |"
            )
        lines.append("")

    if not ridge.empty and not best_rows.empty:
        merged = ridge.merge(best_rows, on=["target_id", "split_name"], suffixes=("_ridge", "_baseline"), how="left")
        lines.append("## Ridge vs Best Baseline")
        lines.append("")
        lines.append("| Target | Split | Best baseline | Ridge entity sp. | Baseline entity sp. | Delta sp. | Ridge NDCG@5 | Baseline NDCG@5 | Delta NDCG@5 | Ridge regret@1 | Baseline regret@1 |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in merged.iterrows():
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {row['model_id_baseline']} | {row['spearman_entity_ridge']:.3f} | {row['spearman_entity_baseline']:.3f} | {(row['spearman_entity_ridge'] - row['spearman_entity_baseline']):+.3f} | {row['ndcg_5_ridge']:.3f} | {row['ndcg_5_baseline']:.3f} | {(row['ndcg_5_ridge'] - row['ndcg_5_baseline']):+.3f} | {row['regret_at_1_ridge']:.2f} | {row['regret_at_1_baseline']:.2f} |"
            )
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
