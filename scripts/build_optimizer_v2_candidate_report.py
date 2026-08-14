from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_prediction_foundation import DB_PATH, ndcg_at_k, top_k_overlap, spearman_corr  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "optimizer_v2_candidate_report.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "OPTIMIZER_V2_CANDIDATE_REPORT.md"


def actuals_for(con: sqlite3.Connection, entity_type: str, ti2026_only: bool) -> pd.DataFrame:
    prefix = "player" if entity_type == "player" else "role_slot"
    extra = "AND ti2026_qualified = 1" if ti2026_only else ""
    mean_df = pd.read_sql_query(
        f"""
        SELECT entity_key, AVG(target_score) AS actual_mean
        FROM dataset_prediction_targets
        WHERE profile_id = 'my_current_banner_official_roles'
          AND target_id = '{prefix}_series_mean'
          AND stage_bucket != 'group_stage'
          {extra}
        GROUP BY entity_key
        """,
        con,
    )
    top1_df = pd.read_sql_query(
        f"""
        SELECT entity_key, AVG(target_score) AS actual_top1
        FROM dataset_prediction_targets
        WHERE profile_id = 'my_current_banner_official_roles'
          AND target_id = '{prefix}_series_top1'
          AND stage_bucket != 'group_stage'
          {extra}
        GROUP BY entity_key
        """,
        con,
    )
    actual = mean_df.merge(top1_df, on="entity_key", how="outer").fillna(0.0)
    actual["actual_test_score"] = 0.60 * actual["actual_mean"].astype(float) + 0.40 * actual["actual_top1"].astype(float)
    return actual[["entity_key", "actual_test_score"]].copy()


def candidate_score(frame: pd.DataFrame, entity_type: str) -> pd.Series:
    if entity_type == "player":
        return (
            0.8 * frame["series_top1_p75"].astype(float)
            + 0.1 * frame["series_mean_p75"].astype(float)
            - 80.0 * frame["top_stat_share"].astype(float)
            - 240.0 * frame["volatility_ratio"].astype(float)
        )
    return (
        0.5 * frame["series_top1_p75"].astype(float)
        + 0.1 * frame["series_mean_p75"].astype(float)
        - 120.0 * frame["sample_weight"].astype(float)
    )


def baseline_score(frame: pd.DataFrame, baseline_id: str) -> pd.Series:
    if baseline_id == "top1_p75_only":
        return frame["series_top1_p75"].astype(float)
    if baseline_id == "ceiling_blend":
        return (
            0.55 * frame["series_top1_p75"].astype(float)
            + 0.25 * frame["series_mean_p75"].astype(float)
            + 0.20 * frame["map_p75_score"].astype(float)
        )
    raise ValueError(baseline_id)


def regret_at_1(actual: pd.Series, predicted: pd.Series) -> float:
    if len(actual) == 0:
        return 0.0
    frame = pd.DataFrame({"actual": actual.astype(float), "predicted": predicted.astype(float)})
    best_idx = frame["predicted"].idxmax()
    return float(frame["actual"].max() - frame.loc[best_idx, "actual"])


def summarize_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "spearman": spearman_corr(actual, predicted),
        "top5_overlap": top_k_overlap(actual, predicted, 5),
        "ndcg_5": ndcg_at_k(actual, predicted, 5),
        "regret_at_1": regret_at_1(actual, predicted),
    }


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        rows: list[dict[str, object]] = []
        segment_rows: list[dict[str, object]] = []
        for entity_type, view in [
            ("player", "analytics_reliable_players_foundation"),
            ("role_slot", "analytics_reliable_role_slots_foundation"),
        ]:
            segcol = "role_group" if entity_type == "player" else "role_slot"
            source = pd.read_sql_query(f"SELECT * FROM {view}", con)
            for ti2026_only, scope in [(False, "all"), (True, "ti2026")]:
                frame = source[source["ti2026_qualified"] == 1].copy() if ti2026_only else source.copy()
                actual = actuals_for(con, entity_type, ti2026_only)
                merged = frame.merge(actual, on="entity_key", how="inner")
                candidate = candidate_score(merged, entity_type)
                for baseline_id in ["top1_p75_only", "ceiling_blend"]:
                    base = baseline_score(merged, baseline_id)
                    metrics = summarize_metrics(merged["actual_test_score"], base)
                    rows.append(
                        {
                            "entity_type": entity_type,
                            "scope": scope,
                            "model_id": baseline_id,
                            **metrics,
                        }
                    )
                metrics = summarize_metrics(merged["actual_test_score"], candidate)
                rows.append(
                    {
                        "entity_type": entity_type,
                        "scope": scope,
                        "model_id": "optimizer_v2_candidate",
                        **metrics,
                    }
                )
                for segment_value, block in merged.groupby(segcol, sort=False):
                    cand_seg = candidate.loc[block.index]
                    segment_rows.append(
                        {
                            "entity_type": entity_type,
                            "scope": scope,
                            "segment": str(segment_value),
                            "model_id": "optimizer_v2_candidate",
                            "spearman": spearman_corr(block["actual_test_score"], cand_seg),
                            "top3_overlap": top_k_overlap(block["actual_test_score"], cand_seg, 3),
                            "ndcg_5": ndcg_at_k(block["actual_test_score"], cand_seg, 5),
                            "regret_at_1": regret_at_1(block["actual_test_score"], cand_seg),
                        }
                    )
        summary = pd.DataFrame(rows)
        segments = pd.DataFrame(segment_rows)
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Optimizer V2 Candidate Report")
    lines.append("")
    lines.append("This report compares a conservative optimizer-v2 candidate against the strongest current simple baselines.")
    lines.append("")
    lines.append("Candidate formulas:")
    lines.append("")
    lines.append("- `player`: `0.8 * series_top1_p75 + 0.1 * series_mean_p75 - 80 * top_stat_share - 240 * volatility_ratio`")
    lines.append("- `role_slot`: `0.5 * series_top1_p75 + 0.1 * series_mean_p75 - 120 * sample_weight`")
    lines.append("")
    lines.append("## Entity Comparison")
    lines.append("")
    lines.append("| Entity type | Scope | Model | Spearman | Top5 overlap | NDCG@5 | Regret@1 |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['scope']} | {row['model_id']} | {row['spearman']:.3f} | {row['top5_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} |"
        )
    lines.append("")
    lines.append("## Segment Diagnostics")
    lines.append("")
    lines.append("| Entity type | Scope | Segment | Model | Spearman | Top3 overlap | NDCG@5 | Regret@1 |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|")
    for _, row in segments.iterrows():
        lines.append(
            f"| {row['entity_type']} | {row['scope']} | {row['segment']} | {row['model_id']} | {row['spearman']:.3f} | {row['top3_overlap']:.3f} | {row['ndcg_5']:.3f} | {row['regret_at_1']:.2f} |"
        )
    lines.append("")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
