"""Small Streamlit demo that runs in a clean clone without private data."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_demo_db import DEFAULT_PATH, build_demo_db


st.set_page_config(page_title="Dota Fantasy Demo", layout="wide")
st.title("Dota 2 Fantasy Analytics: Portable Demo")
st.caption("Synthetic data only. This screen demonstrates the schema, ranking workflow, and reproducible local setup.")

path = build_demo_db(DEFAULT_PATH)
with sqlite3.connect(path) as con:
    leaderboard = pd.read_sql_query("SELECT * FROM analytics_demo_leaderboard", con)
    stats = pd.read_sql_query(
        "SELECT stat_name, ROUND(AVG(fantasy_score), 1) AS avg_points, ROUND(MAX(p75_fantasy_score), 1) AS p75_points FROM analytics_player_maps GROUP BY stat_name ORDER BY p75_points DESC",
        con,
    )

left, right = st.columns(2)
left.subheader("Player leaderboard")
left.dataframe(leaderboard, use_container_width=True, hide_index=True)
right.subheader("Stat profile")
right.bar_chart(stats.set_index("stat_name")[["avg_points", "p75_points"]])

st.info("For the full local system, add the ignored tournament SQLite files and active model artifact, then run `run_rng_human_vs_model_ui.cmd`.")
