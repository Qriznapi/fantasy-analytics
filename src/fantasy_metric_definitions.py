from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


DEFINITIONS: list[tuple[str, str, str, str, str, str, str]] = [
    (
        "fantasy_score",
        "fantasy",
        "player_map",
        "Final fantasy points for one player on one map under the active profile.",
        "sum(selected_stat_base_points * selected_multiplier) + title_bonus_points",
        "Main end result used in most map-level fantasy rankings.",
        "Profile-specific; changes when banner coefficients or active coach titles change.",
    ),
    (
        "base_points_total",
        "fantasy",
        "player_map",
        "Selected-stat x1 fantasy points before profile/banner bonus uplift.",
        "Sum of per-stat base points only for the stats selected by the active profile for that player's official role.",
        "Represents the x1 baseline of the active banner, before extra multiplier uplift above 1.0.",
        "Depends on source coverage quality for some utility stats and on the active profile definition.",
    ),
    (
        "profile_bonus_points",
        "fantasy",
        "player_map",
        "Bonus added by the active fantasy profile on top of base points.",
        "Sum over selected stats of base_points * (multiplier - 1.0) for the player's official role.",
        "Shows how much your specific banner improves a player's map score.",
        "Zero or low if the profile does not emphasize the stats that player hit.",
    ),
    (
        "title_bonus_points",
        "fantasy",
        "player_map",
        "Additional bonus from active coach title rules.",
        "If a configured prefix/suffix condition triggers on that player-map, add fantasy_score_before_titles * bonus_pct.",
        "Captures the extra multiplicative uplift that can explain client-vs-banner residual gaps.",
        "Zero when no title rules are configured or when their conditions do not trigger.",
    ),
    (
        "player_map_score",
        "prediction_foundation",
        "player_map",
        "Prediction-foundation target: player fantasy score on one map.",
        "Identity target equal to fantasy_score for a single player-map row.",
        "Cleanest map-level target for baseline prediction work.",
        "Highly noisy because one map can spike hard.",
    ),
    (
        "player_series_mean",
        "prediction_foundation",
        "player_series",
        "Prediction-foundation target: mean fantasy score across maps in one series.",
        "Average of player_map_score values inside one player-series entity.",
        "Series-level stability target.",
        "Smooths spikes but can understate peak upside.",
    ),
    (
        "player_series_top1",
        "prediction_foundation",
        "player_series",
        "Prediction-foundation target: best single-map fantasy score inside one series.",
        "Maximum player_map_score value inside one player-series entity.",
        "Captures ceiling better than a series average.",
        "Can still be driven by a single outlier map.",
    ),
    (
        "role_slot_map_score",
        "prediction_foundation",
        "role_slot_map",
        "Prediction-foundation target: role-slot fantasy score on one map.",
        "Role-slot aggregate score on one map for core_pair, mid_single, or support_pair.",
        "Useful for fantasy lineup slot analysis instead of individual players only.",
        "Pair slots average multiple players and therefore hide internal asymmetry.",
    ),
    (
        "map_mean_score",
        "reliability_foundation",
        "player_or_role_slot",
        "Average fantasy score per map in the group-stage training sample.",
        "Mean of map target scores for the entity.",
        "Represents typical map-level output.",
        "Less useful than upper quantiles when fantasy format rewards ceiling.",
    ),
    (
        "map_p75_score",
        "reliability_foundation",
        "player_or_role_slot",
        "75th percentile of map fantasy scores in the training sample.",
        "Empirical p75 over map target scores for the entity.",
        "One of the most practical ceiling-without-single-spike metrics.",
        "Needs enough maps to be stable.",
    ),
    (
        "map_p90_score",
        "reliability_foundation",
        "player_or_role_slot",
        "90th percentile of map fantasy scores in the training sample.",
        "Empirical p90 over map target scores for the entity.",
        "More ceiling-focused than p75.",
        "More sensitive to sample size and outliers than p75.",
    ),
    (
        "map_floor_score",
        "reliability_foundation",
        "player_or_role_slot",
        "Worst observed map score in the training sample.",
        "Minimum map score for the entity in group-stage training rows.",
        "Simple downside proxy.",
        "A single disaster map can make it overly pessimistic.",
    ),
    (
        "map_std_score",
        "reliability_foundation",
        "player_or_role_slot",
        "Map-level volatility in raw fantasy points.",
        "Population standard deviation of map scores for the entity.",
        "Higher values mean a swingier pick.",
        "Raw scale depends on point system and role.",
    ),
    (
        "series_mean_avg",
        "reliability_foundation",
        "player_or_role_slot",
        "Average series_mean target in the training sample.",
        "Mean of series-level average scores for the entity.",
        "Series-level stability proxy.",
        "Can underrate explosive but uneven players.",
    ),
    (
        "series_mean_p75",
        "reliability_foundation",
        "player_or_role_slot",
        "75th percentile of series_mean target values.",
        "Empirical p75 over series_mean rows.",
        "Stable high-end series indicator.",
        "Still limited by number of series.",
    ),
    (
        "series_top1_avg",
        "reliability_foundation",
        "player_or_role_slot",
        "Average top-map score per series in the training sample.",
        "Mean of series_top1 target values for the entity.",
        "Blend of ceiling and repeatability.",
        "Can still be lifted by repeated medium spikes rather than elite ones.",
    ),
    (
        "series_top1_p75",
        "reliability_foundation",
        "player_or_role_slot",
        "75th percentile of top-map scores by series.",
        "Empirical p75 over series_top1 rows.",
        "Key ceiling metric for fantasy formats that reward best maps or best series.",
        "Needs enough series to become reliable.",
    ),
    (
        "series_top1_p90",
        "reliability_foundation",
        "player_or_role_slot",
        "90th percentile of top-map scores by series.",
        "Empirical p90 over series_top1 rows.",
        "Aggressive upside signal.",
        "More unstable than p75.",
    ),
    (
        "recent_map_mean_5",
        "reliability_foundation",
        "player_or_role_slot",
        "Short-window recent form at the map level.",
        "Mean of the last five map scores for the entity in training order.",
        "Shows whether late group-stage form was strong.",
        "Very local and therefore noisy.",
    ),
    (
        "recent_series_mean_3",
        "reliability_foundation",
        "player_or_role_slot",
        "Short-window recent form at the series-average level.",
        "Mean of the last three series_mean target values.",
        "Useful when current form matters.",
        "Sensitive to bracket strength and small samples.",
    ),
    (
        "recent_series_top1_3",
        "reliability_foundation",
        "player_or_role_slot",
        "Short-window recent ceiling at the series level.",
        "Mean of the last three series_top1 target values.",
        "Measures whether the entity recently kept hitting high-end maps.",
        "Very small window by design.",
    ),
    (
        "team_segment_strength",
        "reliability_foundation",
        "player_or_role_slot",
        "Team-and-segment context strength for the entity.",
        "Mean series_mean score for the entity's team+segment bucket, with segment/global fallback.",
        "Adds team environment context to individual projections.",
        "Can mix player quality with team ecosystem quality.",
    ),
    (
        "positive_stat_count",
        "reliability_foundation",
        "player_or_role_slot",
        "How many fantasy stats show meaningful positive p75 contribution.",
        "Count of stats whose p75 base-point contribution is positive in the entity stat profile.",
        "Broader positive coverage usually means less brittle fantasy dependence.",
        "Not all positive stats are equally valuable.",
    ),
    (
        "top_stat_share",
        "reliability_foundation",
        "player_or_role_slot",
        "How concentrated the entity is in one dominant fantasy stat.",
        "Largest positive p75 stat contribution divided by the sum of all positive p75 stat contributions.",
        "Higher values mean the fantasy profile depends heavily on one stat family.",
        "Very high concentration can be risky when that stat fails.",
    ),
    (
        "stat_balance_score",
        "reliability_foundation",
        "player_or_role_slot",
        "Breadth-and-balance bonus for a more diversified fantasy profile.",
        "Computed from positive_stat_count breadth times (1 - top_stat_share).",
        "Higher means the entity can score well through several stat paths.",
        "A balanced profile is not automatically a high-ceiling one.",
    ),
    (
        "volatility_ratio",
        "reliability_foundation",
        "player_or_role_slot",
        "Scale-normalized volatility measure.",
        "map_std_score divided by max(map_mean_score, 1), then capped.",
        "Higher means more relative instability around the mean.",
        "Can punish aggressive upside profiles.",
    ),
    (
        "sample_weight",
        "reliability_foundation",
        "player_or_role_slot",
        "Small-sample trust factor.",
        "Monotone weight derived from sample_series, approaching 1 as series count grows.",
        "Higher means the model trusts the observed history more.",
        "Small samples are deliberately shrunk downward.",
    ),
    (
        "reliability_raw_score",
        "reliability_foundation",
        "player_or_role_slot",
        "Unscaled foundation reliability score before 1-100 ranking.",
        "Weighted combination of ceiling, stability, stat-balance, sample-weight, and volatility penalties.",
        "Main internal ranking signal of the foundation reliability layer.",
        "Not calibrated as probability or expected points.",
    ),
    (
        "reliability_score_1_100",
        "reliability_foundation",
        "player_or_role_slot",
        "Segment-relative 1-100 reliability rank.",
        "Rank-scaled version of reliability_raw_score inside role_group or role_slot.",
        "Easy-to-read comparative ranking inside a segment.",
        "Only ordinal within the segment; not comparable as absolute score across very different layers.",
    ),
    (
        "low_estimate",
        "reliability_foundation",
        "player_or_role_slot",
        "Heuristic downside estimate for the entity.",
        "Expected estimate minus penalties from volatility, low sample weight, and concentrated stat dependence, clamped at zero.",
        "Useful for conservative fantasy decision-making.",
        "Not a statistical confidence bound.",
    ),
    (
        "expected_estimate",
        "reliability_foundation",
        "player_or_role_slot",
        "Central heuristic estimate used by the foundation reliability layer.",
        "Non-negative version of reliability_raw_score.",
        "Best single-point summary of the foundation reliability layer.",
        "Not a forecasted exact fantasy total.",
    ),
    (
        "high_estimate",
        "reliability_foundation",
        "player_or_role_slot",
        "Heuristic upside estimate for the entity.",
        "Expected estimate plus bonuses from volatility, sample support, and stat balance.",
        "Useful for ceiling-sensitive fantasy formats.",
        "Not a true upper prediction interval.",
    ),
    (
        "optimizer_raw_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy optimizer's internal score before 1-100 rank scaling.",
        "Weighted blend of best2, second-best2, top2 average, p75, average, floor, minus spike and volatility penalties.",
        "Ranks repeatable high-end series outcomes in the old optimizer.",
        "Built on legacy best2 framing rather than the newer foundation target family.",
    ),
    (
        "optimizer_score_1_100",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy optimizer rank on a 1-100 scale within a segment.",
        "Rank-scaled optimizer_raw_score inside role_group or role_slot.",
        "Human-friendly attractiveness score for the legacy optimizer.",
        "Relative and heuristic, not probabilistic.",
    ),
    (
        "best2_series_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy best-two-maps series score.",
        "Sum of the two best fantasy map scores for the entity inside one series.",
        "Useful for formats where best maps dominate value.",
        "Hard-wired to the old series framing.",
    ),
    (
        "second_best2_series_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Second-best observed legacy best2 series result.",
        "Second highest best2_series_score across training series for the entity.",
        "Main repeatability check against one-off spikes in the old optimizer.",
        "Still inherits all best2 framing limitations.",
    ),
    (
        "top2_series_avg",
        "optimizer_legacy",
        "player_or_role_slot",
        "Average of the two best legacy series outcomes.",
        "Mean of the top two best2_series_score values.",
        "Balances peak and repeatability in the old optimizer.",
        "Needs enough series to be meaningful.",
    ),
    (
        "p75_series_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy p75 over best2 series outcomes.",
        "75th percentile of best2_series_score values.",
        "High-end but not maximal old-optimizer signal.",
        "Still defined on the old target family.",
    ),
    (
        "avg_series_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy average over best2 series outcomes.",
        "Mean of best2_series_score values.",
        "Represents typical old-optimizer series output.",
        "Can undervalue ceiling-first picks.",
    ),
    (
        "std_series_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy series-level volatility.",
        "Population standard deviation of best2_series_score values.",
        "Higher means old-optimizer outcomes vary more across series.",
        "Scale depends on the old target definition.",
    ),
    (
        "floor_series_score",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy minimum best2 series outcome.",
        "Minimum best2_series_score across training series.",
        "Simple old-layer downside proxy.",
        "A single bad series can dominate it.",
    ),
    (
        "spike_gap",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy spike penalty driver.",
        "Difference between best2_series_score and second_best2_series_score.",
        "Larger gap suggests one standout series rather than repeatable dominance.",
        "Only meaningful inside the old best2 framework.",
    ),
    (
        "repeatability_ratio",
        "optimizer_legacy",
        "player_or_role_slot",
        "Legacy repeatability ratio.",
        "second_best2_series_score divided by best2_series_score.",
        "Closer to 1 means a player's high-end output repeated more than once.",
        "Only defined in the legacy optimizer layer.",
    ),
]


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS metric_definitions (
            metric_name TEXT NOT NULL,
            layer_name TEXT NOT NULL,
            entity_scope TEXT NOT NULL,
            short_definition TEXT NOT NULL,
            calculation_summary TEXT NOT NULL,
            interpretation TEXT NOT NULL,
            caveats TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (metric_name, layer_name, entity_scope)
        );

        DROP VIEW IF EXISTS analytics_metric_definitions;
        CREATE VIEW analytics_metric_definitions AS
        SELECT
            metric_name,
            layer_name,
            entity_scope,
            short_definition,
            calculation_summary,
            interpretation,
            caveats,
            created_at_utc
        FROM metric_definitions
        ORDER BY layer_name, metric_name, entity_scope;
        """
    )


def build_metric_definitions(db_path: Path = DB_PATH) -> int:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        now = utc_now()
        con.executemany(
            """
            INSERT OR REPLACE INTO metric_definitions(
                metric_name, layer_name, entity_scope, short_definition,
                calculation_summary, interpretation, caveats, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, now) for row in DEFINITIONS],
        )
        con.commit()
        return len(DEFINITIONS)
    finally:
        con.close()


if __name__ == "__main__":
    count = build_metric_definitions()
    print(f"metric definitions built: {count}")
