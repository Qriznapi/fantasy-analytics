from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"
REQUIRED_FILES = [
    DB_PATH,
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "notebooks" / "ewc2026_fact_agent_demo.ipynb",
    SRC_DIR / "ewc_fact_agent_tools.py",
    SRC_DIR / "fantasy_profile_constructor.py",
    SRC_DIR / "fantasy_banner_optimizer.py",
    PROJECT_ROOT / "dashboard" / "app.py",
    PROJECT_ROOT / "tests" / "regression_tests.py",
    PROJECT_ROOT / "docs" / "ARCHITECTURE.md",
    PROJECT_ROOT / "docs" / "MODELING.md",
    PROJECT_ROOT / "docs" / "DATA_SOURCES.md",
]


def main() -> None:
    print("[files]")
    for path in REQUIRED_FILES:
        print(path, "exists=", path.exists(), "size=", path.stat().st_size if path.exists() else None)
        if not path.exists():
            raise SystemExit(f"Missing required file: {path}")

    sys.path.insert(0, str(SRC_DIR))
    from ewc_fact_agent_tools import ask, db_status, explain_sql_plan, source_urls
    from fantasy_profile_constructor import EXAMPLE_BANNER_SPEC

    print("\n[db_status]")
    print(db_status().to_string(index=False))
    print("\n[constructor roles]", sorted(EXAMPLE_BANNER_SPEC.keys()))

    con = sqlite3.connect(DB_PATH)
    counts = dict(
        con.execute(
            """
            SELECT 'players_v2_recommended', COUNT(*) FROM analytics_reliable_players WHERE recommended_default = 1
            UNION ALL
            SELECT 'role_slots_v2_recommended', COUNT(*) FROM analytics_reliable_role_slots WHERE recommended_default = 1
            UNION ALL
            SELECT 'support_caveat', COUNT(*) FROM analytics_support_caveat
            UNION ALL
            SELECT 'dota_heroes', COUNT(*) FROM dota_heroes
            UNION ALL
            SELECT 'source_cache', COUNT(*) FROM external_source_cache
            UNION ALL
            SELECT 'ti2026_teams', COUNT(*) FROM ti_qualified_teams WHERE event_id='ti2026'
            UNION ALL
            SELECT 'optimizer_ti2026_players', COUNT(*) FROM analytics_optimizer_players WHERE optimizer_scope = 'ti2026'
            UNION ALL
            SELECT 'interval_missing_recommended',
                   (SELECT COUNT(*) FROM analytics_reliable_players WHERE recommended_default = 1 AND (low_estimate IS NULL OR high_estimate IS NULL))
                 + (SELECT COUNT(*) FROM analytics_reliable_role_slots WHERE recommended_default = 1 AND (low_estimate IS NULL OR high_estimate IS NULL))
            UNION ALL
            SELECT 'stable_or_medium_player_intervals', COUNT(*)
            FROM fantasy_reliability_v2_player_predictions
            WHERE confidence_label IN ('stable', 'medium_uncertainty')
            UNION ALL
            SELECT 'public_analytics_views', COUNT(*)
            FROM sqlite_master
            WHERE type='view' AND name LIKE 'analytics_%'
            UNION ALL
            SELECT 'legacy_objects_remaining', COUNT(*)
            FROM sqlite_master
            WHERE name IN (
                'fantasy_reliability_player_predictions',
                'fantasy_reliability_role_slot_predictions',
                'fantasy_reliability_temporal_backtest_predictions',
                'fantasy_reliability_model_evaluation',
                'official_player_overrides',
                'player_identity_sources',
                'source_routing_rules',
                'source_pages',
                'v_external_source_cache_status',
                'v_fantasy_default_player_map_scores',
                'v_fantasy_default_player_map_scores_ti2026_qualified',
                'v_fantasy_default_team_role_map_summary',
                'v_ti2026_qualified_teams',
                'v_fantasy_banner_optimizer_ti2026_players',
                'v_fantasy_reliable_players_top',
                'v_fantasy_reliable_role_slots_top',
                'v_fantasy_reliable_players_v2_recommended',
                'v_fantasy_reliable_role_slots_v2_recommended',
                'v_fantasy_reliability_backtest_default',
                'db_health'
            )
            """
        ).fetchall()
    )
    con.close()
    print("\n[counts]", counts)
    if counts["players_v2_recommended"] != 72:
        raise SystemExit("Unexpected player v2 recommended count")
    if counts["role_slots_v2_recommended"] != 48:
        raise SystemExit("Unexpected role-slot v2 recommended count")
    if counts["dota_heroes"] < 120:
        raise SystemExit("Unexpected hero mapping count")
    if counts["source_cache"] < 10:
        raise SystemExit("Unexpected source cache count")
    if counts["ti2026_teams"] != 16:
        raise SystemExit("Unexpected TI 2026 team count")
    if counts["optimizer_ti2026_players"] <= 0:
        raise SystemExit("No TI 2026 optimizer rows")
    if counts["interval_missing_recommended"] != 0:
        raise SystemExit("Missing reliability intervals in recommended views")
    if counts["stable_or_medium_player_intervals"] <= 0:
        raise SystemExit("No stable/medium confidence labels")
    if counts["public_analytics_views"] < 16:
        raise SystemExit("Unexpected public analytics view count")
    if counts["legacy_objects_remaining"] != 0:
        raise SystemExit("Legacy objects were not cleaned")

    ti_top = ask(
        "top 15 fantasy pos1 players from TI 2026 qualified teams",
        max_rows=5,
    )
    print("\n[ti fantasy route]", ti_top.route)
    print(ti_top.answer_markdown[:1000])
    if ti_top.route != "top_fantasy_maps":
        raise SystemExit("TI filter did not use SQL top_fantasy_maps")

    opt = ask(
        "optimizer banner pos1 players from TI 2026 qualified teams",
        max_rows=5,
    )
    print("\n[optimizer route]", opt.route)
    print(opt.answer_markdown[:1000])
    if opt.route != "banner_optimizer_players":
        raise SystemExit("Optimizer route failed")

    planner = ask(
        "show sql plan for top fantasy pos1 players from TI 2026 qualified teams",
        max_rows=20,
    )
    print("\n[sql planner route]", planner.route)
    print(planner.answer_markdown[:1000])
    if planner.route != "sql_planner":
        raise SystemExit("SQL planner route failed")

    plan_df = explain_sql_plan("top fantasy pos1 players from TI 2026 qualified teams")
    print("\n[sql plan]")
    print(plan_df.to_string(index=False))
    if plan_df.empty or "top_fantasy_maps" not in plan_df.to_string():
        raise SystemExit("SQL planner did not resolve top_fantasy_maps")

    urls = source_urls("команды отобравшиеся на TI 2026")
    print("\n[source urls]")
    print(urls.to_string(index=False))

    print("\n[regression tests]")
    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    import regression_tests

    regression_tests.main()
    print("\nfinal validation passed")


if __name__ == "__main__":
    main()
