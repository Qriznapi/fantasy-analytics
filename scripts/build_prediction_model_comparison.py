from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_model_comparison.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_MODEL_COMPARISON.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        baseline = pd.read_sql_query(
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
        ).groupby(["target_id", "split_name"], as_index=False, sort=False).head(1)
        ridge = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                'ridge_v2' AS model_family,
                r.alpha AS param_a,
                NULL AS param_b,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM ridge_prediction_runs r
            JOIN ridge_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name, r.alpha
            """,
            con,
        )
        quantile = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                'quantile_q50' AS model_family,
                NULL AS param_a,
                NULL AS param_b,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM quantile_prediction_runs r
            JOIN quantile_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name
            """,
            con,
        )
        gbdt = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                'gbdt_rank_v1' AS model_family,
                r.n_estimators AS param_a,
                r.learning_rate AS param_b,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM gbdt_prediction_runs r
            JOIN gbdt_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name, r.n_estimators, r.learning_rate
            """,
            con,
        )
    finally:
        con.close()

    baseline = baseline.assign(model_family="best_baseline", param_a=None, param_b=None)
    baseline = baseline[["target_id", "split_name", "model_family", "param_a", "param_b", "mae", "spearman_entity", "top5_overlap", "ndcg_5", "regret_at_1", "model_id"]]
    ridge["model_id"] = ""
    quantile["model_id"] = ""
    gbdt["model_id"] = ""
    combined = pd.concat([baseline, ridge, quantile, gbdt], ignore_index=True, sort=False)
    winner = combined.sort_values(["target_id", "split_name", "spearman_entity", "ndcg_5", "top5_overlap", "mae"], ascending=[True, True, False, False, False, True])

    lines: list[str] = []
    lines.append("# Prediction Model Comparison")
    lines.append("")
    lines.append("This report compares the best classical baseline against the tuned ridge layer, the quantile q50 point forecast, and the ranking-oriented GBDT experiment.")
    lines.append("")
    for (target_id, split_name), block in winner.groupby(["target_id", "split_name"], sort=False):
        lines.append(f"## {target_id} / {split_name}")
        lines.append("")
        lines.append("| Model | Params | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 | Note |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        for _, row in block.iterrows():
            params = "-"
            if row["model_family"] == "best_baseline":
                params = row["model_id"]
            elif row["model_family"] == "ridge_v2":
                params = f"alpha={row['param_a']:.2f}"
            elif row["model_family"] == "gbdt_rank_v1":
                params = f"trees={int(row['param_a'])}, lr={row['param_b']:.2f}"
            note = "baseline winner" if row["model_family"] == "best_baseline" else ""
            lines.append(
                f"| {row['model_family']} | {params} | {row['mae']:.2f} | {row['spearman_entity']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} | {note} |"
            )
        lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
