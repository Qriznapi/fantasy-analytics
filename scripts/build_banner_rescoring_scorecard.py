from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_banner_rescoring import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "banner_rescoring_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "BANNER_RESCORING_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        players = pd.read_sql_query(
            "SELECT * FROM analytics_banner_rescoring_players WHERE rescoring_scope = 'ti2026' ORDER BY role_group, rescore_score_1_100 DESC, rescore_raw DESC",
            con,
        )
        slots = pd.read_sql_query(
            "SELECT * FROM analytics_banner_rescoring_role_slots WHERE rescoring_scope = 'ti2026' ORDER BY role_slot, rescore_score_1_100 DESC, rescore_raw DESC",
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Banner Rescoring Scorecard")
    lines.append("")
    lines.append(
        "This scorecard summarizes the banner rescoring layer built on top of the production prediction surface plus Monte Carlo diagnostics."
    )
    lines.append("")

    if players.empty and slots.empty:
        lines.append("No banner rescoring rows are available.")
    else:
        for role_group, block in players.groupby("role_group", sort=False):
            lines.append(f"## Top Players / {role_group}")
            lines.append("")
            lines.append("| Player | Team | Rescore | Pred anchor | P90 anchor | P(top3) | Stability | Rank strength |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
            for _, row in block.head(10).iterrows():
                lines.append(
                    f"| {safe_text(row['official_name'])} | {safe_text(row['team_name'])} | {safe_metric(row['rescore_score_1_100'])} | {safe_metric(row['predicted_anchor_score'])} | {safe_metric(row['p90_anchor_score'])} | {safe_metric(row['p_top3_anchor'])} | {safe_metric(row['stability_index'])} | {safe_metric(row['rank_strength_index'])} |"
                )
            lines.append("")

        for role_slot, block in slots.groupby("role_slot", sort=False):
            lines.append(f"## Top Role Slots / {role_slot}")
            lines.append("")
            lines.append("| Players | Team | Rescore | Pred anchor | P90 anchor | P(top3) | Stability | Rank strength |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
            for _, row in block.head(10).iterrows():
                lines.append(
                    f"| {safe_text(row['player_names'])} | {safe_text(row['team_name'])} | {safe_metric(row['rescore_score_1_100'])} | {safe_metric(row['predicted_anchor_score'])} | {safe_metric(row['p90_anchor_score'])} | {safe_metric(row['p_top3_anchor'])} | {safe_metric(row['stability_index'])} | {safe_metric(row['rank_strength_index'])} |"
                )
            lines.append("")

    payload = "\n".join(lines) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    DOCS_MIRROR_PATH.write_text(payload, encoding="utf-8")
    print(str(OUT_PATH))


def safe_metric(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    value = float(value)
    return f"{value:.3f}" if abs(value) < 100 else f"{value:.2f}"


def safe_text(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = str(value).strip()
    return text if text and text.lower() != "nan" else "-"


if __name__ == "__main__":
    main()
