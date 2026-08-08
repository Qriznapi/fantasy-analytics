from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def load_df(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params or [])


def options_from_sql(sql: str) -> list[str]:
    df = load_df(sql)
    if df.empty:
        return []
    return [str(value) for value in df.iloc[:, 0].dropna().tolist()]


def where_clause(
    *,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    stage_bucket: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if position is not None:
        clauses.append("official_position = ?")
        params.append(position)
    if role_group:
        clauses.append("role_group = ?")
        params.append(role_group)
    if team:
        clauses.append("team_name = ?")
        params.append(team)
    if stage_bucket:
        clauses.append("stage_bucket = ?")
        params.append(stage_bucket)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def top_fantasy_maps(
    *,
    ti2026_only: bool,
    position: int | None,
    role_group: str | None,
    team: str | None,
    stage_bucket: str | None,
    limit: int,
) -> pd.DataFrame:
    view = "analytics_player_maps"
    where, params = where_clause(position=position, role_group=role_group, team=team, stage_bucket=stage_bucket)
    if ti2026_only:
        where = (where + " AND " if where else "WHERE ") + "ti2026_qualified = 1"
    return load_df(
        f"""
        SELECT fantasy_score, official_name, team_name, official_position,
               role_group, hero_name, match_date, stage_bucket, stage_name,
               opponent_name, won, duration_sec, qualification_path, ti_region
        FROM {view}
        {where}
        ORDER BY fantasy_score DESC
        LIMIT {int(limit)}
        """,
        params,
    )


def optimizer_players(
    *,
    ti2026_only: bool,
    position: int | None,
    role_group: str | None,
    team: str | None,
    limit: int,
) -> pd.DataFrame:
    view = "analytics_optimizer_players"
    clauses: list[str] = []
    params: list[Any] = []
    clauses.append("optimizer_scope = ?")
    params.append("ti2026" if ti2026_only else "all")
    if position is not None:
        clauses.append("official_position = ?")
        params.append(position)
    if role_group:
        clauses.append("role_group = ?")
        params.append(role_group)
    if team:
        clauses.append("team_name = ?")
        params.append(team)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return load_df(
        f"""
        SELECT optimizer_score_1_100, official_name, team_name,
               official_position, role_group, predicted_score_raw,
               best2_series_score, second_best2_series_score,
               repeatability_ratio, spike_gap, train_series_seen,
               ti2026_qualified, qualification_path, ti_region,
               data_quality_label, recommendation_note
        FROM {view}
        {where}
        ORDER BY optimizer_score_1_100 DESC, predicted_score_raw DESC
        LIMIT {int(limit)}
        """,
        params,
    )


def reliable_players(
    *,
    ti2026_only: bool,
    position: int | None,
    role_group: str | None,
    team: str | None,
    include_support: bool,
    limit: int,
) -> pd.DataFrame:
    view = "analytics_reliable_players"
    clauses: list[str] = []
    params: list[Any] = []
    if not include_support:
        clauses.append("recommended_default = 1")
    if ti2026_only:
        clauses.append("ti2026_qualified = 1")
    if position is not None:
        clauses.append("official_position = ?")
        params.append(position)
    if role_group:
        clauses.append("role_group = ?")
        params.append(role_group)
    if team:
        clauses.append("team_name = ?")
        params.append(team)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return load_df(
        f"""
        SELECT reliability_score_1_100, official_name, team_name,
               official_position, role_group, predicted_score_raw,
               low_estimate, expected_estimate, high_estimate,
               uncertainty_score, confidence_label,
               best2_series_score AS train_best2_series_score,
               second_best2_series_score AS train_second_best2_series_score,
               repeatability_ratio, spike_gap,
               train_series_seen, data_quality_label
        FROM {view}
        {where}
        ORDER BY reliability_score_1_100 DESC, predicted_score_raw DESC
        LIMIT {int(limit)}
        """,
        params,
    )


def reliable_role_slots(*, ti2026_only: bool, role_slot: str | None, team: str | None, limit: int) -> pd.DataFrame:
    view = "analytics_reliable_role_slots"
    clauses: list[str] = []
    params: list[Any] = []
    clauses.append("recommended_default = 1")
    if ti2026_only:
        clauses.append("ti2026_qualified = 1")
    if role_slot:
        clauses.append("role_slot = ?")
        params.append(role_slot)
    if team:
        clauses.append("team_name = ?")
        params.append(team)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return load_df(
        f"""
        SELECT reliability_score_1_100, team_name, role_slot, player_names,
               predicted_score_raw, low_estimate, expected_estimate, high_estimate,
               uncertainty_score, confidence_label,
               best2_series_score AS train_best2_series_score,
               repeatability_ratio, spike_gap, train_series_seen, data_quality_label
        FROM {view}
        {where}
        ORDER BY role_slot, reliability_score_1_100 DESC
        LIMIT {int(limit)}
        """,
        params,
    )


def cli_preview() -> None:
    print(f"DB: {DB_PATH}")
    print("\nTop fantasy maps")
    print(
        top_fantasy_maps(
            ti2026_only=True,
            position=1,
            role_group=None,
            team=None,
            stage_bucket=None,
            limit=10,
        ).to_string(index=False)
    )
    print("\nOptimizer players")
    print(
        optimizer_players(
            ti2026_only=True,
            position=1,
            role_group=None,
            team=None,
            limit=10,
        ).to_string(index=False)
    )
    print("\nReliability with intervals")
    print(
        reliable_players(
            ti2026_only=True,
            position=1,
            role_group=None,
            team=None,
            include_support=False,
            limit=10,
        ).to_string(index=False)
    )


def streamlit_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="EWC 2026 Fantasy Dashboard", layout="wide")
    st.title("EWC 2026 Dota 2 Fantasy Dashboard")
    st.caption("SQLite-first dashboard for fantasy maps, reliability intervals, TI filters and banner optimizer.")

    teams = ["All"] + options_from_sql("SELECT DISTINCT team_name FROM analytics_rosters ORDER BY team_name")
    stages = ["All"] + options_from_sql("SELECT DISTINCT stage_bucket FROM match_stage_registry ORDER BY stage_bucket")
    positions = ["All", "1", "2", "3", "4", "5"]
    role_groups = ["All", "core", "mid", "support"]
    role_slots = ["All", "core_pair", "mid_single", "support_pair"]

    with st.sidebar:
        st.header("Filters")
        ti2026_only = st.checkbox("TI 2026 qualified teams only", value=True)
        position_raw = st.selectbox("Official position", positions)
        role_group_raw = st.selectbox("Role group", role_groups)
        team_raw = st.selectbox("Team", teams)
        stage_raw = st.selectbox("Stage bucket", stages)
        role_slot_raw = st.selectbox("Role slot", role_slots)
        include_support = st.checkbox("Include supports in reliability", value=False)
        limit = st.slider("Rows", min_value=5, max_value=100, value=20, step=5)

    position = None if position_raw == "All" else int(position_raw)
    role_group = None if role_group_raw == "All" else role_group_raw
    team = None if team_raw == "All" else team_raw
    stage_bucket = None if stage_raw == "All" else stage_raw
    role_slot = None if role_slot_raw == "All" else role_slot_raw

    tab_maps, tab_optimizer, tab_reliability, tab_slots, tab_sources = st.tabs(
        ["Top Maps", "Optimizer", "Reliability", "Role Slots", "Sources"]
    )
    with tab_maps:
        st.dataframe(
            top_fantasy_maps(
                ti2026_only=ti2026_only,
                position=position,
                role_group=role_group,
                team=team,
                stage_bucket=stage_bucket,
                limit=limit,
            ),
            use_container_width=True,
            hide_index=True,
        )
    with tab_optimizer:
        st.dataframe(
            optimizer_players(
                ti2026_only=ti2026_only,
                position=position,
                role_group=role_group,
                team=team,
                limit=limit,
            ),
            use_container_width=True,
            hide_index=True,
        )
    with tab_reliability:
        st.info("Intervals are heuristic uncertainty bands around predicted_score_raw, not guaranteed probability bounds.")
        st.dataframe(
            reliable_players(
                ti2026_only=ti2026_only,
                position=position,
                role_group=role_group,
                team=team,
                include_support=include_support,
                limit=limit,
            ),
            use_container_width=True,
            hide_index=True,
        )
    with tab_slots:
        st.dataframe(
            reliable_role_slots(
                ti2026_only=ti2026_only,
                role_slot=role_slot,
                team=team,
                limit=limit,
            ),
            use_container_width=True,
            hide_index=True,
        )
    with tab_sources:
        st.subheader("TI 2026 teams")
        st.dataframe(load_df("SELECT * FROM analytics_ti2026_teams ORDER BY has_ewc_player_data DESC, team_name"), use_container_width=True, hide_index=True)
        st.subheader("External source cache")
        st.dataframe(load_df("SELECT * FROM analytics_sources"), use_container_width=True, hide_index=True)


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"DB file not found: {DB_PATH}")
    try:
        import streamlit  # noqa: F401
    except Exception:
        print("Streamlit is not installed. Showing CLI preview instead.")
        print("Install/run example: pip install streamlit pandas")
        print(f"Then: streamlit run {Path(__file__).resolve()}")
        cli_preview()
        return
    streamlit_app()


if __name__ == "__main__":
    main()
