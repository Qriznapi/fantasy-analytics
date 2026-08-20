from __future__ import annotations

import json
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"


def lines(text: str) -> list[str]:
    if not text.endswith("\n"):
        text += "\n"
    return text.splitlines(keepends=True)


def md_cell(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": lines(text),
    }


def code_cell(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines(text),
    }


def ti_only_block(body: str, message: str) -> str:
    return (
        f'if NOTEBOOK_EVENT_ID != "ti2026":\n'
        f'    print({message!r})\n'
        f'else:\n{textwrap.indent(body, "    ")}'
    )


def setup_cell(
    default_layout: str,
    *,
    default_event_id: str,
    custom_project_root: str | None = None,
    custom_src_dir: str | None = None,
    custom_db_path: str | None = None,
) -> str:
    custom_project_root_literal = "None" if custom_project_root is None else repr(custom_project_root)
    custom_src_dir_literal = "None" if custom_src_dir is None else repr(custom_src_dir)
    custom_db_path_literal = "None" if custom_db_path is None else repr(custom_db_path)
    return f"""from pathlib import Path
import sys
import sqlite3
import pandas as pd

# Layout switch:
# - "project"    : normal repository structure with notebooks/, src/, data/
# - "flat_colab" : files uploaded into one flat runtime directory such as /content
NOTEBOOK_LAYOUT = "{default_layout}"
NOTEBOOK_EVENT_ID = "{default_event_id}"
BENCHMARK_EVENT_ID = "ewc2026"

CUSTOM_PROJECT_ROOT = {custom_project_root_literal}
CUSTOM_SRC_DIR = {custom_src_dir_literal}
CUSTOM_DB_PATH = {custom_db_path_literal}
TI_QUALIFIED_ONLY = NOTEBOOK_EVENT_ID == "ti2026"

EVENT_DB_FILENAMES = {{
    "ewc2026": "ewc_2026_fantasy_compact.sqlite",
    "ti2026": "ti_2026_fantasy_compact.sqlite",
}}
DEFAULT_DB_FILENAME = EVENT_DB_FILENAMES.get(NOTEBOOK_EVENT_ID, EVENT_DB_FILENAMES["ewc2026"])
DEFAULT_BENCHMARK_DB_FILENAME = EVENT_DB_FILENAMES.get(BENCHMARK_EVENT_ID, EVENT_DB_FILENAMES["ewc2026"])


def _unique_paths(items):
    seen = set()
    result = []
    for item in items:
        if item is None:
            continue
        path = Path(item).resolve()
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def candidate_project_roots() -> list[Path]:
    cwd = Path.cwd().resolve()
    candidates = [cwd]
    if cwd.name == "notebooks":
        candidates.append(cwd.parent)
    if CUSTOM_PROJECT_ROOT:
        candidates.insert(0, Path(CUSTOM_PROJECT_ROOT))
    return _unique_paths(candidates)


def resolve_layout() -> tuple[Path, Path, Path]:
    roots = candidate_project_roots()
    if NOTEBOOK_LAYOUT == "project":
        for root in roots:
            src_dir = Path(CUSTOM_SRC_DIR).resolve() if CUSTOM_SRC_DIR else root / "src"
            db_candidates = _unique_paths([
                Path(CUSTOM_DB_PATH) if CUSTOM_DB_PATH else None,
                root / "data" / DEFAULT_DB_FILENAME,
                root / "data" / "db" / DEFAULT_DB_FILENAME,
                root / DEFAULT_DB_FILENAME,
            ])
            for db_path in db_candidates:
                if src_dir.exists() and db_path.exists():
                    return root, src_dir, db_path
        root = roots[0]
        src_dir = Path(CUSTOM_SRC_DIR).resolve() if CUSTOM_SRC_DIR else root / "src"
        db_path = Path(CUSTOM_DB_PATH).resolve() if CUSTOM_DB_PATH else root / "data" / DEFAULT_DB_FILENAME
        return root, src_dir, db_path

    if NOTEBOOK_LAYOUT == "flat_colab":
        root = Path(CUSTOM_PROJECT_ROOT).resolve() if CUSTOM_PROJECT_ROOT else Path.cwd().resolve()
        src_dir = Path(CUSTOM_SRC_DIR).resolve() if CUSTOM_SRC_DIR else (root / "src" if (root / "src").exists() else root)
        db_candidates = _unique_paths([
            Path(CUSTOM_DB_PATH) if CUSTOM_DB_PATH else None,
            root / DEFAULT_DB_FILENAME,
            root / "data" / DEFAULT_DB_FILENAME,
            root / "data" / "db" / DEFAULT_DB_FILENAME,
        ])
        for db_path in db_candidates:
            if db_path.exists():
                return root, src_dir, db_path
        return root, src_dir, db_candidates[0]

    raise ValueError("NOTEBOOK_LAYOUT must be 'project' or 'flat_colab'")


PROJECT_ROOT, SRC_DIR, DB_PATH = resolve_layout()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ewc_fact_agent_tools import (
    EWCFactAgent,
    db_status,
    roster,
    top_fantasy_maps,
    player_maps,
    role_map_summary,
    reliable_players_foundation,
    reliable_role_slots_foundation,
    reliability_backtest_foundation,
    ti_qualified_teams,
    source_cache_status,
    source_urls,
    explain_sql_plan,
    explain_system_short,
    metric_definitions,
    optimizer_backtest_foundation,
    optimizer_v2_players,
    optimizer_v2_role_slots,
    optimizer_v2_backtest,
    banner_optimizer_players,
    banner_optimizer_role_slots,
    banner_optimizer_players_foundation,
    banner_optimizer_role_slots_foundation,
    banner_rescoring_players,
    banner_rescoring_role_slots,
    banner_decision_players,
    banner_decision_role_slots,
    banner_decision_lineups,
    run_sql,
)
from fantasy_profile_constructor import create_or_replace_banner_profile, EXAMPLE_BANNER_SPEC, set_profile_title_rules

agent = EWCFactAgent(DB_PATH)


def ask_foundation(question: str, max_rows: int | None = None, use_llm: bool = False):
    result = agent.ask(question, max_rows=max_rows, use_llm=use_llm)
    print(result.answer_markdown)
    return result


def sql_df(query: str, params=None):
    return run_sql(query, params=params or [], con=agent.con)


def resolve_db_path_for_event(event_id: str) -> Path:
    filename = EVENT_DB_FILENAMES[event_id]
    if NOTEBOOK_LAYOUT == "flat_colab":
        root = Path(CUSTOM_PROJECT_ROOT).resolve() if CUSTOM_PROJECT_ROOT else Path.cwd().resolve()
        candidates = _unique_paths([
            root / filename,
            root / "data" / filename,
            root / "data" / "db" / filename,
        ])
    else:
        root = PROJECT_ROOT
        candidates = _unique_paths([
            root / "data" / filename,
            root / "data" / "db" / filename,
            root / filename,
        ])
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


BENCHMARK_DB_PATH = resolve_db_path_for_event(BENCHMARK_EVENT_ID)


def sql_df_from_db(db_path, query: str, params=None):
    con = sqlite3.connect(str(db_path))
    try:
        return pd.read_sql_query(query, con, params=params or [])
    finally:
        con.close()


def scorecard_text(filename: str) -> str:
    for base in [PROJECT_ROOT / "reports", PROJECT_ROOT / "docs", PROJECT_ROOT]:
        path = base / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
    return f"Scorecard not found: {{filename}}"


def json_text(path_like: str) -> str:
    path = Path(path_like)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.read_text(encoding="utf-8")


if NOTEBOOK_LAYOUT == "flat_colab":
    DASHBOARD_PATH = PROJECT_ROOT / "app.py"
    TESTS_PATH = PROJECT_ROOT / "regression_tests.py"
else:
    DASHBOARD_PATH = PROJECT_ROOT / "dashboard" / "app.py"
    TESTS_PATH = PROJECT_ROOT / "tests" / "regression_tests.py"

print("Layout mode:", NOTEBOOK_LAYOUT)
print("Notebook event:", NOTEBOOK_EVENT_ID)
print("Benchmark event:", BENCHMARK_EVENT_ID)
print("Project root:", PROJECT_ROOT)
print("Source dir:", SRC_DIR)
print("Database path:", DB_PATH)
print("Benchmark DB path:", BENCHMARK_DB_PATH)
if NOTEBOOK_EVENT_ID == "ti2026" and BENCHMARK_EVENT_ID != "ewc2026":
    print("Warning: TI 2026 is currently intended as an inference target; benchmark defaults are expected to stay on ewc2026.")
print(explain_system_short())
"""


def notebook_cells(default_layout: str, *, demo: bool) -> list[dict]:
    title = "# EWC 2026 Dota 2 fact-agent"
    intro = """This notebook is synchronized with the current compact Project F database and helper layer.

It exposes:

- official player identities and positions;
- player-map and role-slot fantasy scores;
- foundation reliability tables;
- optimizer foundation and optimizer v2;
- production prediction and Monte Carlo outputs;
- unified evaluation across prediction / optimizer / reliability / simulation;
- banner rescoring and practical banner decision layers.

Use `NOTEBOOK_LAYOUT` in the first code cell to switch between repository mode and a flat Colab upload layout.
Use `NOTEBOOK_EVENT_ID` to choose which tournament database is opened by default: `ti2026` or `ewc2026`.

Current note:

- EWC replay-derived metrics are already merged into the compact database.
- TI replay and browser-assisted replay probes are wired in the repository, but `watchers_taken` / `lotus` may still remain source-missing for TI until public `.dem.bz2` archives become available.
"""

    ask_examples = """examples = [
    "what roster did BetBoom use?",
    "top 15 fantasy pos1 players among TI 2026 qualified teams",
    "show the best core_pair combinations among TI 2026 qualified teams",
    "show banner rescoring for core role slots from TI 2026 teams",
    "give a balanced lineup decision for TI 2026",
    "which stats are approximate and which are fully covered?",
    "what stages are marked as group stage versus playoff?",
]

for question in examples:
    print("-", question)
"""

    cells = [
        md_cell(f"{title}\n\n{intro}"),
        code_cell(
            setup_cell(
                default_layout,
                default_event_id="ewc2026" if demo else "ti2026",
                custom_project_root="/content" if demo else None,
                custom_src_dir="/content" if demo else None,
                custom_db_path=None,
            )
        ),
        md_cell("## 1. Database status\n\nRun this first to confirm that the active SQLite file and helper layer are aligned."),
        code_cell("display(db_status(con=agent.con))"),
        md_cell("## 1a. TI live maintenance\n\nThis block is only relevant when `NOTEBOOK_EVENT_ID = \"ti2026\"`. It prints the maintenance commands for the live TI database."),
        code_cell(
            """if NOTEBOOK_EVENT_ID != "ti2026":
    print("This block is only needed for the live TI 2026 workflow.")
else:
    print("Incremental TI sync:")
    print(f"{sys.executable} {PROJECT_ROOT / 'scripts' / 'sync_ti2026_matches.py'} --write-status-report")
    print()
    print("Standalone TI status report:")
    print(f"{sys.executable} {PROJECT_ROOT / 'scripts' / 'report_ti2026_status.py'} --write-markdown")
    print()
    print("TI database validation:")
    print(f"{sys.executable} {PROJECT_ROOT / 'scripts' / 'validate_ti2026_database.py'}")
"""
        ),
        md_cell("## 2. Metric reference\n\nThese rows explain how the stored foundation metrics are defined and how they should be interpreted."),
        code_cell(
            """metric_cols = [
    "metric_name",
    "layer_name",
    "entity_scope",
    "short_definition",
    "calculation_summary",
    "interpretation",
    "caveats",
]

display(metric_definitions(con=agent.con)[metric_cols].head(12))
display(metric_definitions("stat_balance_score", con=agent.con)[metric_cols])
display(metric_definitions("volatility_ratio", con=agent.con)[metric_cols])
"""
        ),
        md_cell("## 3. Natural-language routes\n\nThese are example questions that the deterministic source-first agent can now answer directly from the project database."),
        code_cell(ask_examples),
        md_cell("## 4. Core helpers\n\nThese helpers expose the main fact tables directly, without going through the question router."),
        code_cell(
            """display(roster("Team Falcons", con=agent.con))
display(top_fantasy_maps(position=1, ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(reliable_players_foundation(position=1, ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(reliable_role_slots_foundation(role_slot="core_pair", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(ti_qualified_teams(con=agent.con))
"""
        ),
        md_cell("## 4a. Selected player under one or more banners\n\nUse this block to inspect one player across all maps under one or more scoring profiles. It shows per-match totals plus per-stat weighted contributions for each selected banner."),
        code_cell(
            """PLAYER_TO_INSPECT = "Nisha"
PLAYER_PROFILE_IDS = [
    "my_current_banner_official_roles",
]

player_banner_maps = sql_df(
    \"\"\"
    SELECT profile_id, match_date, match_id, series_id, stage_name, team_name, opponent_name,
           official_name, official_position, role_group, hero_name, won, duration_sec,
           base_points_total, profile_bonus_points, title_bonus_points, fantasy_score
    FROM fantasy_player_map_scores
    WHERE official_name = ?
      AND profile_id IN ({placeholders})
    ORDER BY profile_id, match_date, match_id
    \"\"\".format(placeholders=",".join("?" for _ in PLAYER_PROFILE_IDS)),
    [PLAYER_TO_INSPECT, *PLAYER_PROFILE_IDS],
)

player_banner_stats_long = sql_df(
    \"\"\"
    SELECT m.profile_id, m.match_date, m.match_id, m.series_id, m.stage_name,
           m.team_name, m.opponent_name, m.official_name, m.hero_name,
           s.stat_name, s.raw_value, s.base_points, ps.multiplier,
           ROUND(s.base_points * ps.multiplier, 2) AS weighted_points
    FROM fantasy_player_map_scores m
    JOIN fantasy_player_map_stat_points s
      ON s.match_id = m.match_id
     AND s.account_id = m.account_id
     AND s.team_name = m.team_name
    JOIN fantasy_scoring_profile_stats ps
      ON ps.profile_id = m.profile_id
     AND ps.role_scope = m.role_group
     AND ps.stat_name = s.stat_name
     AND ps.enabled = 1
    WHERE m.official_name = ?
      AND m.profile_id IN ({placeholders})
    ORDER BY m.profile_id, m.match_date, m.match_id, weighted_points DESC, s.stat_name
    \"\"\".format(placeholders=",".join("?" for _ in PLAYER_PROFILE_IDS)),
    [PLAYER_TO_INSPECT, *PLAYER_PROFILE_IDS],
)

player_banner_stats_wide = (
    player_banner_stats_long
    .pivot_table(
        index=[
            "profile_id", "match_date", "match_id", "series_id", "stage_name",
            "team_name", "opponent_name", "official_name", "hero_name"
        ],
        columns="stat_name",
        values="weighted_points",
        aggfunc="sum",
        fill_value=0.0,
    )
    .reset_index()
)

player_banner_summary = sql_df(
    \"\"\"
    SELECT profile_id,
           COUNT(*) AS maps_played,
           ROUND(AVG(fantasy_score), 2) AS avg_fantasy_score,
           ROUND(MAX(fantasy_score), 2) AS best_map_score,
           ROUND(
               MAX(CASE WHEN row_num = 1 THEN fantasy_score END) +
               MAX(CASE WHEN row_num = 2 THEN fantasy_score END),
               2
           ) AS best_two_maps_sum
    FROM (
        SELECT profile_id, fantasy_score,
               ROW_NUMBER() OVER (PARTITION BY profile_id ORDER BY fantasy_score DESC, match_id DESC) AS row_num
        FROM fantasy_player_map_scores
        WHERE official_name = ?
          AND profile_id IN ({placeholders})
    )
    GROUP BY profile_id
    ORDER BY avg_fantasy_score DESC, best_map_score DESC
    \"\"\".format(placeholders=",".join("?" for _ in PLAYER_PROFILE_IDS)),
    [PLAYER_TO_INSPECT, *PLAYER_PROFILE_IDS],
)

display(player_banner_summary)
display(player_banner_maps)
display(player_banner_stats_wide)
display(player_banner_stats_long)
"""
        ),
        md_cell("## 4b. Players strong on both EWC and TI\n\nThis block compares the same scoring profile across the two local compact databases and ranks players who look strong in both tournaments, not just one of them."),
        code_cell(
            """CROSS_EVENT_PROFILE_ID = "my_current_banner_official_roles"
CROSS_EVENT_MIN_MAPS = 3

ewc_db_path = resolve_db_path_for_event("ewc2026")
ti_db_path = resolve_db_path_for_event("ti2026")

cross_event_query = \"\"\"
WITH player_event AS (
    SELECT official_name, official_position, role_group,
           COUNT(*) AS maps_played,
           ROUND(AVG(fantasy_score), 2) AS avg_score,
           ROUND(MAX(fantasy_score), 2) AS best_score,
           ROUND(
               AVG(CASE WHEN percentile_bucket >= 75 THEN fantasy_score END),
               2
           ) AS top_quarter_avg
    FROM (
        SELECT official_name, official_position, role_group, fantasy_score,
               NTILE(4) OVER (
                   PARTITION BY official_name, official_position, role_group
                   ORDER BY fantasy_score
               ) * 25 AS percentile_bucket
        FROM fantasy_player_map_scores
        WHERE profile_id = ?
    )
    GROUP BY official_name, official_position, role_group
    HAVING COUNT(*) >= ?
)
SELECT * FROM player_event
\"\"\"

ewc_event = sql_df_from_db(ewc_db_path, cross_event_query, [CROSS_EVENT_PROFILE_ID, CROSS_EVENT_MIN_MAPS])
ti_event = sql_df_from_db(ti_db_path, cross_event_query, [CROSS_EVENT_PROFILE_ID, CROSS_EVENT_MIN_MAPS])

ewc_event = ewc_event.rename(columns={
    "maps_played": "ewc_maps",
    "avg_score": "ewc_avg",
    "best_score": "ewc_best",
    "top_quarter_avg": "ewc_top_quarter_avg",
})
ti_event = ti_event.rename(columns={
    "maps_played": "ti_maps",
    "avg_score": "ti_avg",
    "best_score": "ti_best",
    "top_quarter_avg": "ti_top_quarter_avg",
})

cross_event_players = ewc_event.merge(
    ti_event,
    on=["official_name", "official_position", "role_group"],
    how="inner",
)

if not cross_event_players.empty:
    for col in ["ewc_avg", "ewc_best", "ewc_top_quarter_avg", "ti_avg", "ti_best", "ti_top_quarter_avg"]:
        cross_event_players[f"{col}_rank"] = cross_event_players[col].rank(method="dense", ascending=False)
    cross_event_players["two_event_strength"] = (
        cross_event_players["ewc_avg_rank"]
        + cross_event_players["ewc_top_quarter_avg_rank"]
        + cross_event_players["ti_avg_rank"]
        + cross_event_players["ti_top_quarter_avg_rank"]
    )
    cross_event_players = cross_event_players.sort_values(
        ["two_event_strength", "ti_top_quarter_avg", "ewc_top_quarter_avg", "ti_best", "ewc_best"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)

display(cross_event_players)
"""
        ),
        md_cell("## 5. Reliability foundation\n\nThis is the baseline reliability layer with interval estimates and confidence context."),
        code_cell(
            """player_cols = [
    "reliability_score_1_100",
    "official_name",
    "team_name",
    "official_position",
    "predicted_score_raw",
    "low_estimate",
    "expected_estimate",
    "high_estimate",
    "confidence_label",
]
slot_cols = [
    "reliability_score_1_100",
    "team_name",
    "role_slot",
    "player_names",
    "predicted_score_raw",
    "low_estimate",
    "expected_estimate",
    "high_estimate",
    "confidence_label",
]

display(reliable_players_foundation(position=1, ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con)[player_cols])
display(reliable_role_slots_foundation(role_slot="core_pair", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con)[slot_cols])
display(reliability_backtest_foundation(con=agent.con))
"""
        ),
        md_cell("## 6. Optimizer foundation and optimizer v2\n\nThe legacy foundation optimizer remains as a comparison surface. The default optimizer helpers now point to optimizer v2."),
        code_cell(
            """display(banner_optimizer_players_foundation(position=1, ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(banner_optimizer_role_slots_foundation(role_slot="core_pair", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(optimizer_backtest_foundation(con=agent.con))

display(optimizer_v2_players(position=1, ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(optimizer_v2_role_slots(role_slot="core_pair", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(optimizer_v2_backtest(con=agent.con))
"""
        ),
        md_cell("## 7. Production prediction and Monte Carlo\n\nThese are the current predictive surfaces used for score forecasting and ranking stability."),
        code_cell(
            """display(sql_df(\"\"\"
SELECT split_name, target_id, chosen_family, chosen_model_id,
       official_name, team_name, official_position, role_group,
       predicted_score, q75, metric_entity_spearman, metric_ndcg_5
FROM analytics_prediction_production_players
ORDER BY split_name, target_id, predicted_score DESC
LIMIT 10
\"\"\"))

display(sql_df(\"\"\"
SELECT target_id, split_name, official_name, team_name, official_position, role_group,
       predicted_score, p_top1, p_top3, p_top5, expected_rank, simulated_std_score
FROM analytics_prediction_monte_carlo_players
WHERE ti2026_qualified = 1
ORDER BY target_id, split_name, p_top1 DESC, p_top3 DESC, predicted_score DESC
LIMIT 10
\"\"\"))
"""
        ),
        md_cell("## 8. Prediction model quality comparison\n\nThis block compares the main prediction families on the same targets and splits so you can see which models actually rank entities better."),
        code_cell(
            """display(sql_df(\"\"\"
WITH baseline AS (
    SELECT
        r.target_id,
        r.split_name,
        'best_baseline' AS model_family,
        r.model_id AS model_config,
        MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
        MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
        MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
        MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
        MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
    FROM foundation_prediction_runs r
    JOIN foundation_evaluation_reports e
      ON e.run_id = r.run_id
    GROUP BY r.target_id, r.split_name, r.model_id
),
best_baseline AS (
    SELECT *
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY target_id, split_name
                   ORDER BY spearman_entity DESC, ndcg_5 DESC, top5_overlap DESC, mae ASC
               ) AS rn
        FROM baseline
    )
    WHERE rn = 1
),
ridge AS (
    SELECT
        r.target_id,
        r.split_name,
        'ridge_v2' AS model_family,
        'alpha=' || printf('%.2f', r.alpha) AS model_config,
        MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
        MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
        MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
        MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
        MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
    FROM ridge_prediction_runs r
    JOIN ridge_evaluation_reports e
      ON e.run_id = r.run_id
    GROUP BY r.target_id, r.split_name, r.alpha
),
quantile AS (
    SELECT
        r.target_id,
        r.split_name,
        'quantile_q50' AS model_family,
        'q50' AS model_config,
        MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
        MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
        MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
        MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
        MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
    FROM quantile_prediction_runs r
    JOIN quantile_evaluation_reports e
      ON e.run_id = r.run_id
    GROUP BY r.target_id, r.split_name
),
gbdt AS (
    SELECT
        r.target_id,
        r.split_name,
        'gbdt_rank_v1' AS model_family,
        'trees=' || CAST(r.n_estimators AS TEXT) || ', lr=' || printf('%.2f', r.learning_rate) AS model_config,
        MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
        MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
        MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
        MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
        MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
    FROM gbdt_prediction_runs r
    JOIN gbdt_evaluation_reports e
      ON e.run_id = r.run_id
    GROUP BY r.target_id, r.split_name, r.n_estimators, r.learning_rate
),
combined AS (
    SELECT
        target_id,
        split_name,
        model_family,
        model_config,
        mae,
        spearman_entity,
        top5_overlap,
        ndcg_5,
        regret_at_1
    FROM best_baseline
    UNION ALL
    SELECT
        target_id,
        split_name,
        model_family,
        model_config,
        mae,
        spearman_entity,
        top5_overlap,
        ndcg_5,
        regret_at_1
    FROM ridge
    UNION ALL
    SELECT
        target_id,
        split_name,
        model_family,
        model_config,
        mae,
        spearman_entity,
        top5_overlap,
        ndcg_5,
        regret_at_1
    FROM quantile
    UNION ALL
    SELECT
        target_id,
        split_name,
        model_family,
        model_config,
        mae,
        spearman_entity,
        top5_overlap,
        ndcg_5,
        regret_at_1
    FROM gbdt
)
SELECT
    target_id,
    split_name,
    model_family,
    model_config,
    ROUND(spearman_entity, 3) AS spearman_entity,
    ROUND(ndcg_5, 3) AS ndcg_5,
    ROUND(top5_overlap, 3) AS top5_overlap,
    ROUND(mae, 2) AS mae,
    ROUND(regret_at_1, 2) AS regret_at_1
FROM combined
ORDER BY target_id, split_name, spearman_entity DESC, ndcg_5 DESC, top5_overlap DESC, mae ASC
\"\"\"))

print("\\n" + "=" * 80 + "\\n")
print(scorecard_text("prediction_model_comparison.md")[:3000])
"""
        ),
        md_cell("## 9. Unified evaluation\n\nThis layer puts prediction, optimizer, reliability, and simulation outputs onto one comparison scoreboard."),
        code_cell(
            """display(sql_df(\"\"\"
SELECT layer_group, surface_family, surface_name, entity_type, task_group,
       target_id, split_name, optimizer_scope,
       spearman_entity, ndcg_5, top5_overlap,
       COALESCE(mae_entity, mae_row) AS mae,
       regret_at_1
FROM analytics_unified_evaluation_leaderboard
WHERE comparable_flag = 1
ORDER BY ndcg_5 DESC, spearman_entity DESC
LIMIT 15
\"\"\"))

display(sql_df(\"\"\"
SELECT layer_group, surface_family, surface_name, entity_type, target_id, split_name,
       avg_p_top1, avg_p_top3, avg_p_top5, avg_simulated_std_score
FROM analytics_unified_evaluation_leaderboard
WHERE comparable_flag = 0
ORDER BY avg_p_top1 DESC, avg_p_top3 DESC
LIMIT 15
\"\"\"))
"""
        ),
        md_cell("## 10. Banner rescoring\n\nBanner rescoring is the first practical post-prediction layer. It blends predicted ceiling, ranking strength, and stability into a single 1-100 recommendation score."),
        code_cell(
            """display(banner_rescoring_players(position=1, ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(banner_rescoring_role_slots(role_slot="core_pair", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))

_ = ask_foundation("show banner rescoring for core role slots from TI 2026 teams", max_rows=10)
"""
        ),
        md_cell("## 11. Banner decision layer\n\nBanner decision turns rescoring into actionable recommendations for conservative, balanced, and aggressive risk profiles."),
        code_cell(
            """display(banner_decision_players(position=1, risk_profile="balanced", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(banner_decision_role_slots(role_slot="core_pair", risk_profile="balanced", ti2026_only=TI_QUALIFIED_ONLY, limit=10, con=agent.con))
display(banner_decision_lineups(risk_profile="balanced", ti2026_only=TI_QUALIFIED_ONLY, limit=5, con=agent.con))

_ = ask_foundation("give a balanced lineup decision for TI 2026", max_rows=10)
"""
        ),
        md_cell("## 12. Coverage and provenance\n\nThese views show which metrics are complete, approximated, or still source-sensitive."),
        code_cell(
            """display(source_cache_status(con=agent.con))
display(source_urls("teams qualified to TI 2026", con=agent.con))

display(sql_df(\"\"\"
SELECT stat_name, preferred_source, coverage_status,
       has_stage_evidence, is_row_complete, nonzero_raw_rows,
       source_missing_rows, objective_derived_rows
FROM analytics_fantasy_backfill_coverage
ORDER BY
    CASE coverage_status
        WHEN 'filled_backfill' THEN 1
        WHEN 'filled_approximation' THEN 2
        WHEN 'source_needed' THEN 3
        ELSE 4
    END,
    stat_name
\"\"\"))
"""
        ),
        md_cell("## 13. SQL planner\n\nUse this when you want to see how the deterministic agent decomposes a complex question before any optional LLM polishing."),
        code_cell("""display(explain_sql_plan("top 15 fantasy pos1 players from TI 2026 qualified teams", con=agent.con))"""),
        md_cell("## 14. Scorecard previews\n\nThe project also mirrors the main analytical summaries into markdown scorecards under `reports/` and `docs/`."),
        code_cell(
            """print(scorecard_text("unified_evaluation_scorecard.md")[:3000])
print("\\n" + "=" * 80 + "\\n")
print(scorecard_text("banner_rescoring_scorecard.md")[:2500])
print("\\n" + "=" * 80 + "\\n")
print(scorecard_text("banner_decision_scorecard.md")[:2500])
"""
        ),
        md_cell("## 15. Custom banner profile example\n\nUse this if you want to rescore the tournament under your own stat multipliers."),
        code_cell(
            """MY_CUSTOM_BANNER = {
    "core": [
        ("kills", 2.5),
        ("creep_score", 2.5),
        ("teamfight_participation", 1.8),
    ],
    "mid": [
        ("creep_score", 2.7),
        ("runes_grabbed", 1.8),
        ("teamfight_participation", 2.7),
    ],
    "support": [
        ("lotus", 3.2),
        ("watchers_taken", 2.1),
        ("teamfight_participation", 1.5),
    ],
}

MY_CUSTOM_BANNER
"""
        ),
        md_cell("## 16. Mid head-to-head under the current banner\n\nThis block compares `Nisha` and `bzm` under the notebook's current mid banner. It is designed for the TI 2026 workflow and will self-skip on other event databases."),
        code_cell(
            ti_only_block(
                """MID_COMPARE_PROFILE_ID = create_or_replace_banner_profile(
    agent.con,
    "example_constructor_same_as_current",
    EXAMPLE_BANNER_SPEC,
    profile_name="Example profile from constructor",
    description="Current notebook banner profile",
    set_default=False,
    commit=True,
)

pick_value_compare = sql_df(
    \"\"\"
    SELECT official_name, team_name, maps_seen,
           total_fantasy_score, avg_score, best_score, floor_score,
           avg_abs_deviation, consistency_score, ceiling_score, pick_value_score
    FROM fantasy_pick_value
    WHERE profile_id = ?
      AND official_name IN ('Nisha', 'bzm')
    ORDER BY official_name
    \"\"\",
    [MID_COMPARE_PROFILE_ID],
)

series_compare = sql_df(
    \"\"\"
    WITH series_scores AS (
        SELECT profile_id, official_name, team_name,
               COALESCE(CAST(series_id AS TEXT), 'match:' || CAST(match_id AS TEXT)) AS series_key,
               fantasy_score,
               ROW_NUMBER() OVER (
                   PARTITION BY profile_id, official_name, team_name, COALESCE(CAST(series_id AS TEXT), 'match:' || CAST(match_id AS TEXT))
                   ORDER BY fantasy_score DESC, match_id DESC
               ) AS rn
        FROM fantasy_player_map_scores
        WHERE profile_id = ?
          AND official_name IN ('Nisha', 'bzm')
    )
    SELECT official_name, team_name,
           COUNT(DISTINCT series_key) AS series_seen,
           ROUND(AVG(fantasy_score), 2) AS avg_map_score,
           ROUND(AVG(CASE WHEN rn <= 2 THEN fantasy_score END), 2) AS avg_top2_map_score,
           ROUND(MAX(CASE WHEN rn = 1 THEN fantasy_score END), 2) AS best_series_top1
    FROM series_scores
    GROUP BY official_name, team_name
    ORDER BY official_name
    \"\"\",
    [MID_COMPARE_PROFILE_ID],
)

stat_compare = sql_df(
    \"\"\"
    SELECT m.official_name, m.team_name, sp.stat_name,
           ROUND(AVG(sp.base_points), 2) AS avg_base_points,
           ROUND(MAX(sp.base_points), 2) AS max_base_points,
           ROUND(AVG(sp.base_points * ps.multiplier), 2) AS avg_weighted_points,
           ROUND(MAX(sp.base_points * ps.multiplier), 2) AS max_weighted_points
    FROM fantasy_player_map_scores m
    JOIN fantasy_player_map_stat_points sp
      ON sp.match_id = m.match_id
     AND sp.account_id = m.account_id
     AND sp.team_name = m.team_name
    JOIN fantasy_scoring_profile_stats ps
      ON ps.profile_id = m.profile_id
     AND ps.stat_name = sp.stat_name
     AND ps.role_scope = 'mid'
    WHERE m.profile_id = ?
      AND m.official_name IN ('Nisha', 'bzm')
      AND sp.stat_name IN ('creep_score', 'runes_grabbed', 'teamfight_participation')
    GROUP BY m.official_name, m.team_name, sp.stat_name
    ORDER BY m.official_name, sp.stat_name
    \"\"\",
    [MID_COMPARE_PROFILE_ID],
)

layer_compare = sql_df(
    \"\"\"
    SELECT 'foundation' AS layer, official_name, team_name,
           reliability_score_1_100 AS score_1_100,
           expected_estimate AS anchor_1,
           high_estimate AS anchor_2,
           series_top1_p75 AS anchor_3,
           volatility_ratio AS risk_or_vol,
           confidence_label AS note
    FROM analytics_reliable_players_foundation
    WHERE official_name IN ('Nisha', 'bzm')

    UNION ALL

    SELECT 'optimizer_v2_ti2026', official_name, team_name,
           optimizer_v2_score_1_100,
           optimizer_v2_raw_score,
           series_mean_p75,
           series_top1_p75,
           volatility_ratio,
           CAST(sample_weight AS TEXT)
    FROM analytics_optimizer_v2_players
    WHERE optimizer_scope = 'ti2026'
      AND official_name IN ('Nisha', 'bzm')

    UNION ALL

    SELECT 'rescoring_ti2026', official_name, team_name,
           rescore_score_1_100,
           predicted_anchor_score,
           p90_anchor_score,
           p_top3_anchor,
           stability_index,
           CAST(rank_strength_index AS TEXT)
    FROM analytics_banner_rescoring_players
    WHERE rescoring_scope = 'ti2026'
      AND official_name IN ('Nisha', 'bzm')

    UNION ALL

    SELECT 'decision_balanced_ti2026', official_name, team_name,
           decision_score_1_100,
           decision_raw,
           NULL,
           NULL,
           NULL,
           rationale
    FROM analytics_banner_decision_players
    WHERE decision_scope = 'ti2026'
      AND risk_profile = 'balanced'
      AND official_name IN ('Nisha', 'bzm')

    UNION ALL

    SELECT 'mc_series_mean_temporal', official_name, team_name,
           predicted_score,
           p_top1,
           p_top3,
           p_top5,
           simulated_std_score,
           CAST(expected_rank AS TEXT)
    FROM analytics_prediction_monte_carlo_players
    WHERE target_id = 'player_series_mean'
      AND split_name = 'temporal_60_40'
      AND official_name IN ('Nisha', 'bzm')

    UNION ALL

    SELECT 'mc_series_top1_temporal', official_name, team_name,
           predicted_score,
           p_top1,
           p_top3,
           p_top5,
           simulated_std_score,
           CAST(expected_rank AS TEXT)
    FROM analytics_prediction_monte_carlo_players
    WHERE target_id = 'player_series_top1'
      AND split_name = 'temporal_60_40'
      AND official_name IN ('Nisha', 'bzm')
    ORDER BY layer, official_name
    \"\"\"
)

top_maps_compare = sql_df(
    \"\"\"
    SELECT official_name, team_name, match_date, stage_name, hero_name, fantasy_score
    FROM fantasy_player_map_scores
    WHERE profile_id = ?
      AND official_name IN ('Nisha', 'bzm')
    ORDER BY official_name, fantasy_score DESC
    LIMIT 12
    \"\"\",
    [MID_COMPARE_PROFILE_ID],
)

display(pick_value_compare)
display(series_compare)
display(stat_compare)
display(layer_compare)
display(top_maps_compare)
""",
                "This head-to-head block is configured for TI 2026 and is skipped for the current event.",
            )
        ),
        md_cell("## 17. Coach title template\n\nUse this block if you want to inspect the generic title template or the ready TI 2026 ruleset for `Cerulean + the Clutch`. On non-TI runs it will only show the generic template."),
        code_cell(
            """TITLE_TEMPLATE_PATH = PROJECT_ROOT / "configs" / "title_rules" / "the_clutch_template.json"
TITLE_RULESET_PATH = PROJECT_ROOT / "configs" / "title_rules" / "cerulean_the_clutch_ti2026.json"
print("Generic template:")
if TITLE_TEMPLATE_PATH.exists():
    print(json_text(str(TITLE_TEMPLATE_PATH)))
else:
    print("Title template JSON is not available in this notebook layout.")
if NOTEBOOK_EVENT_ID == "ti2026" and TITLE_RULESET_PATH.exists():
    print()
    print("Ready TI 2026 ruleset:")
    print(json_text(str(TITLE_RULESET_PATH)))
else:
    print()
    print("TI-specific title rules are not available for this notebook layout or event.")
"""
        ),
        md_cell("## 18. Apply / compare title rules\n\nThis example applies the TI 2026 title ruleset to a profile and compares map scores before and after the title layer. It self-skips on non-TI databases."),
        code_cell(
            ti_only_block(
                '''import json

TITLE_COMPARE_PROFILE_ID = "ti2026_cerulean_nothingtogay_client_banner"
TITLE_COMPARE_PLAYER = "Nisha"

title_rules_path = PROJECT_ROOT / "configs" / "title_rules" / "cerulean_the_clutch_ti2026.json"
if not title_rules_path.exists():
    print("TI 2026 title rules JSON is not available in this notebook layout.")
else:
    title_spec = json.loads(json_text(str(title_rules_path)))

    # Example edits:
    # title_spec[0]["bonus_pct"] = 11.0
    # title_spec[1]["bonus_pct"] = 16.0

    set_profile_title_rules(agent.con, TITLE_COMPARE_PROFILE_ID, title_spec, commit=True)

    title_compare = sql_df(
        """
        SELECT official_name, team_name, match_date, stage_name, hero_name,
               won, base_points_total, profile_bonus_points, title_bonus_points, fantasy_score
        FROM fantasy_player_map_scores
        WHERE profile_id = ?
          AND official_name = ?
        ORDER BY match_date, match_id
        LIMIT 20
        """,
        [TITLE_COMPARE_PROFILE_ID, TITLE_COMPARE_PLAYER],
    )

    display(title_compare)
''',
                "This title-rule comparison block is configured for TI 2026 and is skipped for the current event.",
            )
        ),
        md_cell("## 19. Dashboard and tests\n\nThe notebook keeps the interactive dashboard and regression tests outside of the notebook body on purpose."),
        code_cell(
            """print("Dashboard launch command:")
print(f"streamlit run {DASHBOARD_PATH}")
print()
print("Regression tests launch command:")
print(f"{sys.executable} {TESTS_PATH}")
"""
        ),
        md_cell("## 20. Optional GigaChat post-processing\n\nDeterministic SQL-first answers remain the default. If your environment has `GIGACHAT_CREDENTIALS`, you can ask the same question with `use_llm=True` to turn the factual draft into a more polished answer without changing the underlying numbers."),
        code_cell("""# Example:\n# ask_foundation("show reliable fantasy candidates for TI 2026", use_llm=True)"""),
    ]

    if demo:
        cells.insert(
            8,
            md_cell("## Demo note\n\nThis demo notebook is the same analytical surface as the main fact-agent notebook, but it defaults to `flat_colab` so it can be uploaded directly into a single Colab runtime directory."),
        )
    return cells


def notebook_metadata() -> dict:
    return {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12",
        },
    }


def write_notebook(path: Path, cells: list[dict]) -> None:
    payload = {
        "cells": cells,
        "metadata": notebook_metadata(),
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    write_notebook(NOTEBOOKS_DIR / "02_fact_agent.ipynb", notebook_cells("project", demo=False))
    write_notebook(NOTEBOOKS_DIR / "ewc2026_fact_agent_colab.ipynb", notebook_cells("flat_colab", demo=True))
    print("synced notebooks:")
    print(NOTEBOOKS_DIR / "02_fact_agent.ipynb")
    print(NOTEBOOKS_DIR / "ewc2026_fact_agent_colab.ipynb")


if __name__ == "__main__":
    main()
