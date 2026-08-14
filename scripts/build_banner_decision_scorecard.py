from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_banner_decision import DB_PATH  # noqa: E402


OUT_PATH = PROJECT_ROOT / "reports" / "banner_decision_scorecard.md"
DOCS_MIRROR_PATH = PROJECT_ROOT / "docs" / "BANNER_DECISION_SCORECARD.md"


def main() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        slots = pd.read_sql_query(
            "SELECT * FROM analytics_banner_decision_role_slots WHERE decision_scope = 'ti2026' ORDER BY risk_profile, role_slot, decision_score_1_100 DESC, decision_raw DESC",
            con,
        )
        lineups = pd.read_sql_query(
            "SELECT * FROM analytics_banner_decision_lineups WHERE decision_scope = 'ti2026' ORDER BY risk_profile, lineup_rank",
            con,
        )
    finally:
        con.close()

    lines: list[str] = []
    lines.append("# Banner Decision Scorecard")
    lines.append("")
    lines.append(
        "This scorecard summarizes the practical decision layer for banner selection. It uses banner rescoring outputs and converts them into conservative, balanced, and aggressive role-slot recommendations plus ready-made three-team lineups."
    )
    lines.append("")

    if slots.empty and lineups.empty:
        lines.append("No banner decision rows are available.")
    else:
        for risk_profile, block in slots.groupby("risk_profile", sort=False):
            lines.append(f"## Role-slot picks / {risk_profile}")
            lines.append("")
            lines.append("| Role slot | Team | Players | Score | Raw |")
            lines.append("|---|---|---|---:|---:|")
            for _, row in block.groupby("role_slot", sort=False).head(5).iterrows():
                lines.append(
                    f"| {safe_text(row['role_slot'])} | {safe_text(row['team_name'])} | {safe_text(row['player_names'])} | {safe_metric(row['decision_score_1_100'])} | {safe_metric(row['decision_raw'])} |"
                )
            lines.append("")

        for risk_profile, block in lineups.groupby("risk_profile", sort=False):
            lines.append(f"## Top lineups / {risk_profile}")
            lines.append("")
            lines.append("| Rank | Core | Mid | Support | Score |")
            lines.append("|---:|---|---|---|---:|")
            for _, row in block.head(10).iterrows():
                core = f"{safe_text(row['core_team_name'])}: {safe_text(row['core_players'])}"
                mid = f"{safe_text(row['mid_team_name'])}: {safe_text(row['mid_player'])}"
                support = f"{safe_text(row['support_team_name'])}: {safe_text(row['support_players'])}"
                lines.append(
                    f"| {int(row['lineup_rank'])} | {core} | {mid} | {support} | {safe_metric(row['lineup_score_1_100'])} |"
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
