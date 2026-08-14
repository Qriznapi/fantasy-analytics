from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "prediction_quantile_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "PREDICTION_QUANTILE_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                MAX(CASE WHEN e.metric_name = 'mae' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'pinball_q25' THEN e.metric_value END) AS pinball_q25,
                MAX(CASE WHEN e.metric_name = 'pinball_q50' THEN e.metric_value END) AS pinball_q50,
                MAX(CASE WHEN e.metric_name = 'pinball_q75' THEN e.metric_value END) AS pinball_q75,
                MAX(CASE WHEN e.metric_name = 'coverage_q75' THEN e.metric_value END) AS coverage_q75,
                MAX(CASE WHEN e.metric_name = 'coverage_q90' THEN e.metric_value END) AS coverage_q90,
                MAX(CASE WHEN e.metric_name = 'band_width_q25_q75' THEN e.metric_value END) AS band_width_q25_q75
            FROM quantile_prediction_runs r
            JOIN quantile_evaluation_reports e
              ON e.run_id = r.run_id
            GROUP BY r.target_id, r.split_name
            ORDER BY r.target_id, r.split_name
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Prediction Quantile Scorecard")
    lines.append("")
    lines.append("This scorecard summarizes the linear quantile layer built on the shared richer feature foundation. The point estimate is q50, while q25/q75/q90 expose distribution shape and coverage behavior.")
    lines.append("")
    if summary.empty:
        lines.append("No quantile evaluation rows are available.")
    else:
        lines.append("| Target | Split | MAE(q50) | Entity sp. | Pinball q25 | Pinball q50 | Pinball q75 | Coverage q75 | Coverage q90 | Band q25-q75 |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in summary.iterrows():
            lines.append(
                f"| {row['target_id']} | {row['split_name']} | {row['mae']:.2f} | {row['spearman_entity']:.3f} | {row['pinball_q25']:.2f} | {row['pinball_q50']:.2f} | {row['pinball_q75']:.2f} | {row['coverage_q75']:.3f} | {row['coverage_q90']:.3f} | {row['band_width_q25_q75']:.2f} |"
            )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
