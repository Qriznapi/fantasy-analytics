from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"


def fail(message: str) -> None:
    raise AssertionError(message)


def assert_equal(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        fail(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"[ok] {name}: {actual!r}")


def assert_at_least(name: str, actual: int | float, minimum: int | float) -> None:
    if actual < minimum:
        fail(f"{name}: expected >= {minimum!r}, got {actual!r}")
    print(f"[ok] {name}: {actual!r}")


def assert_zero(name: str, actual: int | float) -> None:
    assert_equal(name, actual, 0)


def scalar(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return con.execute(sql, params).fetchone()[0]


def test_files() -> None:
    required = [
        DB_PATH,
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "notebooks" / "ewc2026_fact_agent_demo.ipynb",
        SRC_DIR / "ewc_fact_agent_tools.py",
        SRC_DIR / "fantasy_profile_constructor.py",
        SRC_DIR / "fantasy_banner_optimizer.py",
        PROJECT_ROOT / "dashboard" / "app.py",
        PROJECT_ROOT / "docs" / "ARCHITECTURE.md",
        PROJECT_ROOT / "docs" / "MODELING.md",
    ]
    for path in required:
        if not path.exists():
            fail(f"missing required file: {path}")
        print(f"[ok] file exists: {path.relative_to(PROJECT_ROOT)}")


def test_database_invariants() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        integrity = scalar(con, "PRAGMA integrity_check")
        assert_equal("sqlite integrity_check", integrity, "ok")

        assert_equal("matches", scalar(con, "SELECT COUNT(*) FROM matches"), 157)
        assert_equal("player_identity_registry", scalar(con, "SELECT COUNT(*) FROM player_identity_registry"), 120)
        assert_equal("analytics player map rows", scalar(con, "SELECT COUNT(*) FROM analytics_player_maps"), 1570)
        assert_equal("analytics team role map rows", scalar(con, "SELECT COUNT(*) FROM analytics_team_role_maps"), 314)
        assert_equal("analytics v2 player recommended rows", scalar(con, "SELECT COUNT(*) FROM analytics_reliable_players WHERE recommended_default = 1"), 72)
        assert_equal("analytics v2 role-slot recommended rows", scalar(con, "SELECT COUNT(*) FROM analytics_reliable_role_slots WHERE recommended_default = 1"), 48)
        assert_equal("ti2026 teams", scalar(con, "SELECT COUNT(*) FROM ti_qualified_teams WHERE event_id='ti2026'"), 16)
        assert_at_least("dota heroes", scalar(con, "SELECT COUNT(*) FROM dota_heroes"), 120)
        assert_at_least("external source cache rows", scalar(con, "SELECT COUNT(*) FROM external_source_cache"), 10)
        assert_at_least("analytics optimizer TI player rows", scalar(con, "SELECT COUNT(*) FROM analytics_optimizer_players WHERE optimizer_scope = 'ti2026'"), 1)
        assert_at_least("public analytics view count", scalar(con, "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name LIKE 'analytics_%'"), 16)

        legacy_objects = [
            "fantasy_reliability_player_predictions",
            "fantasy_reliability_role_slot_predictions",
            "fantasy_reliability_temporal_backtest_predictions",
            "fantasy_reliability_model_evaluation",
            "official_player_overrides",
            "player_identity_sources",
            "source_routing_rules",
            "source_pages",
            "v_external_source_cache_status",
            "v_fantasy_default_player_map_scores",
            "v_fantasy_default_player_map_scores_ti2026_qualified",
            "v_fantasy_default_team_role_map_summary",
            "v_ti2026_qualified_teams",
            "v_fantasy_banner_optimizer_ti2026_players",
            "v_fantasy_reliable_players_top",
            "v_fantasy_reliable_role_slots_top",
            "v_fantasy_reliable_players_v2_recommended",
            "v_fantasy_reliable_role_slots_v2_recommended",
            "v_fantasy_reliability_backtest_default",
            "db_health",
        ]
        placeholders = ",".join("?" for _ in legacy_objects)
        legacy_count = scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE name IN ({placeholders})
            """,
            tuple(legacy_objects),
        )
        assert_zero("removed legacy object count", legacy_count)

        assert_zero(
            "missing hero names in default fantasy view",
            scalar(
                con,
                "SELECT COUNT(*) FROM analytics_player_maps WHERE hero_name IS NULL OR hero_name = ''",
            ),
        )
        assert_zero(
            "missing duration in default fantasy view",
            scalar(
                con,
                "SELECT COUNT(*) FROM analytics_player_maps WHERE duration_sec IS NULL OR duration_sec = 0",
            ),
        )
        assert_zero(
            "supports in default player reliability recommendations",
            scalar(
                con,
                """
                SELECT COUNT(*)
                FROM analytics_reliable_players
                WHERE recommended_default = 1
                  AND (role_group = 'support' OR official_position IN (4, 5))
                """,
            ),
        )
        assert_zero(
            "support_pair in default role-slot reliability recommendations",
            scalar(
                con,
                """
                SELECT COUNT(*)
                FROM analytics_reliable_role_slots
                WHERE recommended_default = 1
                  AND role_slot = 'support_pair'
                """,
            ),
        )
        assert_zero(
            "missing reliability intervals in recommended rows",
            scalar(
                con,
                """
                SELECT
                    (SELECT COUNT(*) FROM analytics_reliable_players WHERE recommended_default = 1 AND (low_estimate IS NULL OR high_estimate IS NULL))
                  + (SELECT COUNT(*) FROM analytics_reliable_role_slots WHERE recommended_default = 1 AND (low_estimate IS NULL OR high_estimate IS NULL))
                """,
            ),
        )
        assert_at_least(
            "stable-or-medium player confidence labels",
            scalar(
                con,
                """
                SELECT COUNT(*)
                FROM fantasy_reliability_v2_player_predictions
                WHERE confidence_label IN ('stable', 'medium_uncertainty')
                """,
            ),
            1,
        )

        max_formula_diff = scalar(
            con,
            """
            SELECT MAX(ABS((base_points_total + profile_bonus_points) - fantasy_score))
            FROM analytics_player_maps
            """,
        )
        if max_formula_diff is None:
            fail("formula integrity query returned NULL")
        if float(max_formula_diff) > 0.02:
            fail(f"formula max diff too high: {max_formula_diff}")
        print(f"[ok] fantasy formula max diff: {float(max_formula_diff):.6f}")
    finally:
        con.close()


def test_agent_routes() -> None:
    sys.path.insert(0, str(SRC_DIR))
    from ewc_fact_agent_tools import ask, explain_sql_plan

    ti_top = ask("top 15 fantasy pos1 players from TI 2026 qualified teams", max_rows=5)
    assert_equal("agent route: TI fantasy top", ti_top.route, "top_fantasy_maps")

    optimizer = ask("optimizer banner pos1 players from TI 2026 qualified teams", max_rows=5)
    assert_equal("agent route: optimizer", optimizer.route, "banner_optimizer_players")

    sources = ask("show source cache", max_rows=5)
    assert_equal("agent route: source cache", sources.route, "source_cache_status")

    planner = ask("show sql plan for top fantasy pos1 players from TI 2026 qualified teams", max_rows=20)
    assert_equal("agent route: sql planner", planner.route, "sql_planner")

    plan_df = explain_sql_plan("top fantasy pos1 players from TI 2026 qualified teams")
    if plan_df.empty:
        fail("SQL planner returned empty dataframe")
    keys = set(plan_df["key"].astype(str).tolist())
    for required_key in {"route", "tables_or_views", "filters", "sql"}:
        if required_key not in keys:
            fail(f"SQL planner missing key: {required_key}")
    print("[ok] SQL planner keys:", sorted(keys))


def main() -> None:
    test_files()
    test_database_invariants()
    test_agent_routes()
    print("\nALL REGRESSION TESTS PASSED")


if __name__ == "__main__":
    main()
