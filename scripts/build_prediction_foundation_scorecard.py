from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_foundation_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_FOUNDATION_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                r.model_id,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'spearman' AND e.metric_scope = 'row' THEN e.metric_value END) AS spearman_row,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM foundation_prediction_runs r
            JOIN foundation_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name, r.model_id
            ORDER BY r.target_id, r.split_name, mae ASC, spearman_entity DESC
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Prediction Foundation Scorecard")
    lines.append("")
    lines.append("This scorecard summarizes the new map-first prediction foundation layer. It is intended as the baseline comparison surface that will replace the old best2-only framing over time.")
    lines.append("")
    if summary.empty:
        lines.append("No foundation evaluation rows are available.")
    else:
        for (target_id, split_name), block in summary.groupby(["target_id", "split_name"], sort=False):
            lines.append(f"## {target_id} / {split_name}")
            lines.append("")
            lines.append("| Model | MAE | Spearman row | Spearman entity | Top5 overlap | Regret@1 |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for _, row in block.head(5).iterrows():
                lines.append(
                    f"| {row['model_id']} | {row['mae']:.2f} | {row['spearman_row']:.3f} | {row['spearman_entity']:.3f} | {row['top5_overlap']:.3f} | {row['regret_at_1']:.2f} |"
                )
            lines.append("")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
