from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "unified_evaluation_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "UNIFIED_EVALUATION_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        comparable = pd.read_sql_query(
            """
            SELECT *
            FROM analytics_unified_evaluation_leaderboard
            WHERE comparable_flag = 1
            """,
            con,
        )
        diagnostics = pd.read_sql_query(
            """
            SELECT *
            FROM analytics_unified_evaluation_leaderboard
            WHERE comparable_flag = 0
            """,
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Unified Evaluation Scorecard")
    lines.append("")
    lines.append(
        "This scorecard is the unified evaluation surface for Project F. It normalizes prediction, reliability, optimizer, and simulation layers into one comparison registry."
    )
    lines.append("")

    if comparable.empty and diagnostics.empty:
        lines.append("No unified evaluation rows are available.")
    else:
        lines.append("## Comparable Backtests")
        lines.append("")
        lines.append("| Layer | Family | Surface | Entity | Task | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE | Regret@1 |")
        lines.append("|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|")
        for _, row in comparable.iterrows():
            lines.append(
                f"| {safe_text(row['layer_group'])} | {safe_text(row['surface_family'])} | {safe_text(row['surface_name'])} | {safe_text(row['entity_type'])} | {safe_text(row['task_group'])} | {safe_text(row['target_id'])} | {safe_text(row['split_name'])} | {safe_text(row['optimizer_scope'])} | {safe_metric(row['spearman_entity'])} | {safe_metric(row['ndcg_5'])} | {safe_metric(row['top5_overlap'])} | {safe_metric(row['mae_entity'], row['mae_row'])} | {safe_metric(row['regret_at_1'])} |"
            )
        lines.append("")

        for key, block in comparable.groupby(["task_group", "entity_type"], sort=False):
            task_group, entity_type = key
            lines.append(f"## Best Surfaces / {task_group} / {entity_type}")
            lines.append("")
            lines.append("| Family | Surface | Target | Split | Scope | Spearman | NDCG@5 | Top5 | MAE |")
            lines.append("|---|---|---|---|---|---:|---:|---:|---:|")
            for _, row in block.head(8).iterrows():
                lines.append(
                    f"| {safe_text(row['surface_family'])} | {safe_text(row['surface_name'])} | {safe_text(row['target_id'])} | {safe_text(row['split_name'])} | {safe_text(row['optimizer_scope'])} | {safe_metric(row['spearman_entity'])} | {safe_metric(row['ndcg_5'])} | {safe_metric(row['top5_overlap'])} | {safe_metric(row['mae_entity'], row['mae_row'])} |"
                )
            lines.append("")

        if not diagnostics.empty:
            lines.append("## Diagnostic-only Layers")
            lines.append("")
            lines.append("| Layer | Family | Surface | Entity | Target | Split | Avg p_top1 | Avg p_top3 | Avg p_top5 | Avg sim std |")
            lines.append("|---|---|---|---|---|---|---:|---:|---:|---:|")
            for _, row in diagnostics.iterrows():
                lines.append(
                    f"| {safe_text(row['layer_group'])} | {safe_text(row['surface_family'])} | {safe_text(row['surface_name'])} | {safe_text(row['entity_type'])} | {safe_text(row['target_id'])} | {safe_text(row['split_name'])} | {safe_metric(row['avg_p_top1'])} | {safe_metric(row['avg_p_top3'])} | {safe_metric(row['avg_p_top5'])} | {safe_metric(row['avg_simulated_std_score'])} |"
                )
            lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


def safe_metric(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        if pd.isna(value):
            continue
        return f"{float(value):.3f}" if abs(float(value)) < 100 else f"{float(value):.2f}"
    return "-"


def safe_text(value: object) -> str:
    if value is None:
        return "-"
    if pd.isna(value):
        return "-"
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return "-"
    return text


if __name__ == "__main__":
    main()
