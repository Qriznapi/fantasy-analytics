from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_gbdt_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_GBDT_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                r.n_estimators,
                r.learning_rate,
                MAX(CASE WHEN e.metric_name = 'mae' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'ndcg_5' THEN e.metric_value END) AS ndcg_5,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' THEN e.metric_value END) AS regret_at_1
            FROM gbdt_prediction_runs r
            JOIN gbdt_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name, r.n_estimators, r.learning_rate
            ORDER BY r.target_id, r.split_name
            """,
            con,
        )
        importance = pd.read_sql_query(
            """
            SELECT
                target_id,
                split_name,
                feature_name,
                total_gain,
                split_count
            FROM analytics_prediction_gbdt_importance
            ORDER BY target_id, split_name, total_gain DESC, split_count DESC
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Prediction GBDT Scorecard")
    lines.append("")
    lines.append("This scorecard summarizes the lightweight ranking-oriented GBDT experiment. It is not LambdaMART; it is a boosted-stump regressor with target-aware sample weights to emphasize high-value fantasy outcomes.")
    lines.append("")
    if summary.empty:
        lines.append("No GBDT evaluation rows are available.")
    else:
        lines.append("| Target | Split | Trees | LR | MAE | Entity sp. | Top5 overlap | NDCG@5 | Regret@1 |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in summary.iterrows():
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {int(row['n_estimators'])} | {row['learning_rate']:.3f} | {row['mae']:.2f} | {row['spearman_entity']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} |"
            )
        lines.append("")
    if not importance.empty:
        for (target_id, split_name), block in importance.groupby(["target_id", "split_name"], sort=False):
            lines.append(f"## Top Features / {target_id} / {split_name}")
            lines.append("")
            lines.append("| Feature | Total gain | Split count |")
            lines.append("|---|---:|---:|")
            for _, row in block.head(8).iterrows():
                lines.append(f"| {row['feature_name']} | {row['total_gain']:.2f} | {int(row['split_count'])} |")
            lines.append("")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
