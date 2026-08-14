from __future__ import annotations

import json
import os
import re
import sqlite3
import textwrap
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)

SUPPORT_CAVEAT_RU = (
    "Support-метрики теперь входят в обычные fantasy-оценки и reliability-рейтинги. "
    "Их utility-статы чуть сильнее зависят от контекста карты, поэтому их полезно читать вместе с source coverage."
)

DEFAULT_RELIABILITY_SCOPE_RU = (
    "Default foundation reliability теперь включает все роли, включая support. "
    "Для саппортов полезно дополнительно смотреть на source coverage и тип метрик, а не только на итоговый score."
)

TEAM_ALIASES = {
    "betboom": "BoomBoys",
    "bet boom": "BoomBoys",
    "bb": "BoomBoys",
    "falcons": "Team Falcons",
    "liquid": "Team Liquid",
    "spirit": "Team Spirit",
    "pvision": "PVISION",
    "parivision": "PVISION",
    "xtreme": "Xtreme Gaming",
    "virtus": "Virtus.pro",
    "vp": "Virtus.pro",
    "yandex": "Team Yandex",
    "vici": "Vici Gaming",
    "gl": "GamerLegion",
}


@dataclass
class AgentResult:
    question: str
    route: str
    answer_markdown: str
    dataframes: dict[str, pd.DataFrame] = field(default_factory=dict)
    plan: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)


@dataclass
class SQLPlan:
    question: str
    route: str
    intent: str
    tables_or_views: list[str]
    filters: dict[str, Any] = field(default_factory=dict)
    metrics: list[str] = field(default_factory=list)
    sql: str | None = None
    params: list[Any] = field(default_factory=list)
    missing_external_facts: list[str] = field(default_factory=list)
    confidence: str = "medium"
    notes: list[str] = field(default_factory=list)


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def run_sql(sql: str, params: tuple[Any, ...] | list[Any] | None = None, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        return pd.read_sql_query(sql, con, params=params or [])
    finally:
        if own:
            con.close()


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
            (name,),
        ).fetchone()
        is not None
    )


def df_block(df: pd.DataFrame, max_rows: int = 12) -> str:
    if df.empty:
        return "_РќРµС‚ СЃС‚СЂРѕРє РїРѕРґ СЌС‚РѕС‚ Р·Р°РїСЂРѕСЃ._"
    shown = df.head(max_rows)
    return "```text\n" + shown.to_string(index=False) + "\n```"


def render_answer(title: str, df: pd.DataFrame, max_rows: int = 12, note: str | None = None) -> str:
    parts = [f"### {title}", "", df_block(df, max_rows)]
    if len(df) > max_rows:
        parts.append(f"\nРџРѕРєР°Р·Р°РЅРѕ {max_rows} РёР· {len(df)} СЃС‚СЂРѕРє.")
    if note:
        parts.extend(["", note])
    return "\n".join(parts)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("С‘", "Рµ")).strip()


def extract_limit(question: str, default: int = 15) -> int:
    q = normalize_text(question)
    m = re.search(r"\bС‚РѕРї\s*(\d+)\b|\btop\s*(\d+)\b", q)
    if not m:
        return default
    value = int(next(group for group in m.groups() if group))
    return max(1, min(value, 100))


def extract_position(question: str) -> int | None:
    q = normalize_text(question)
    raw = re.sub(r"\s+", " ", question.lower()).strip()
    patterns = [
        r"\bpos\s*([1-5])\b",
        r"\bposition\s*([1-5])\b",
        r"\b([1-5])\s*position\b",
        r"\bпозици[ия]\s*([1-5])\b",
        r"\b([1-5])\s*позици[яи]\b",
        r"\b([1-5])\s*поз\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            return int(m.group(1))
        m = re.search(pattern, raw)
        if m:
            return int(m.group(1))
    return None


def extract_role_group(question: str) -> str | None:
    q = normalize_text(question)
    raw = question.lower()
    if any(token in q for token in ["СЃР°Рї", "СЃР°РїРїРѕСЂС‚", "support", "pos4", "pos5"]) or any(
        token in raw for token in ["сап", "саппорт", "support", "4 пози", "5 пози", "pos4", "pos5"]
    ):
        return "support"
    if any(token in q for token in ["РјРёРґ", "mid", "РјРёРґРµСЂ", "pos2"]) or any(
        token in raw for token in ["мид", "мидер", "mid", "2 пози", "pos2"]
    ):
        return "mid"
    if any(token in q for token in ["РєРѕСЂ", "core", "РєРµСЂСЂРё", "carry", "offlane", "РѕС„С„Р»РµР№РЅ", "pos1", "pos3"]) or any(
        token in raw for token in ["кор", "керри", "carry", "оффлейн", "core", "1 пози", "3 пози", "pos1", "pos3"]
    ):
        return "core"
    return None


def position_to_role_group(position: int | None) -> str | None:
    if position in {1, 3}:
        return "core"
    if position == 2:
        return "mid"
    if position in {4, 5}:
        return "support"
    return None


def support_requested(question: str) -> bool:
    role = extract_role_group(question)
    pos = extract_position(question)
    return role == "support" or pos in {4, 5}


def ti_filter_requested(question: str) -> bool:
    q = normalize_text(question)
    raw = question.lower()
    return any(token in q for token in ["ti 2026", "the international", "РѕС‚РѕР±СЂР°РІ", "РєРІР°Р»РёС„РёС†"]) or any(
        token in raw for token in ["ti 2026", "the international", "отобрав", "квалифиц", "инт", "international"]
    )


def optimizer_requested(question: str) -> bool:
    q = normalize_text(question)
    raw = question.lower()
    return any(token in q for token in ["РѕРїС‚РёРј", "optimizer", "Р±Р°РЅРЅРµСЂ", "banner", "РєРѕРіРѕ СЃС‚Р°РІРёС‚СЊ", "РєРѕРіРѕ Р±СЂР°С‚СЊ"]) or any(
        token in raw for token in ["оптим", "баннер", "optimizer", "banner", "кого ставить", "кого брать"]
    )


def extract_role_slot(question: str) -> str | None:
    q = normalize_text(question)
    if any(token in q for token in ["support_pair", "support pair", "РїР°СЂР° СЃР°Рї", "СЃР°Рї РїР°СЂС‹", "СЃР°РїРїРѕСЂС‚ РїР°СЂС‹"]):
        return "support_pair"
    if any(token in q for token in ["core_pair", "core pair", "РїР°СЂР° РєРѕСЂ", "РєРѕСЂ РїР°СЂС‹", "core РїР°СЂС‹", "РєРѕСЂС‹"]):
        return "core_pair"
    if any(token in q for token in ["mid_single", "mid single", "РјРёРґ СЃР»РѕС‚", "РјРёРґРµСЂ"]):
        return "mid_single"
    return None


def extract_stage_bucket(question: str) -> str | None:
    q = normalize_text(question)
    if any(token in q for token in ["РїР»РµР№РѕС„С„", "РїР»РµР№-РѕС„С„", "playoff", "playoffs"]):
        return "playoffs"
    if any(token in q for token in ["РіСЂСѓРїРїР°", "РіСЂСѓРїРїРѕРІ", "group", "survival"]):
        return "group_stage"
    return None


def resolve_team(question_or_team: str, con: sqlite3.Connection) -> str | None:
    q = normalize_text(question_or_team)
    for alias, canonical in TEAM_ALIASES.items():
        if alias in q:
            return canonical
    teams = [row[0] for row in con.execute("SELECT DISTINCT team_name FROM player_identity_registry ORDER BY team_name")]
    for team in teams:
        if normalize_text(team) in q:
            return team
    tokens = [token for token in re.split(r"[^a-zA-Z0-9_.`-]+", question_or_team) if len(token) >= 2]
    for team in teams:
        normalized = normalize_text(team)
        if any(normalize_text(token) == normalized for token in tokens):
            return team
    return None


def extract_player(question: str, con: sqlite3.Connection) -> str | None:
    q = normalize_text(question)
    names = [row[0] for row in con.execute("SELECT DISTINCT official_name FROM player_identity_registry ORDER BY LENGTH(official_name) DESC")]
    for name in names:
        if normalize_text(name) in q:
            return name
    return None


def decompose_question(question: str, con: sqlite3.Connection) -> list[str]:
    q = normalize_text(question)
    steps: list[str] = []
    team = resolve_team(question, con)
    player = None if team else extract_player(question, con)
    pos = extract_position(question)
    role = extract_role_group(question)
    stage = extract_stage_bucket(question)
    limit = extract_limit(question)
    if any(token in q for token in ["РЅР°РґРµР¶", "РЅР°РґeР¶", "СЃС‚Р°Р±РёР»", "РїРёРє", "РІС‹Р±РѕСЂ", "reliable"]):
        steps.append("РћРїСЂРµРґРµР»РёС‚СЊ, С‡С‚Рѕ СЌС‚Рѕ Р·Р°РїСЂРѕСЃ РЅР° reliability fantasy-РїРёРєР°.")
    if any(token in q for token in ["С„РµРЅС‚РµР·Рё", "С„СЌРЅС‚РµР·Рё", "fantasy"]):
        steps.append("РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ fantasy-РїСЂРѕС„РёР»СЊ Рё СЃРѕС…СЂР°РЅРµРЅРЅС‹Рµ fantasy_score РёР· SQLite.")
    if team:
        steps.append(f"РћС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ РєРѕРјР°РЅРґСѓ: {team}.")
    if player:
        steps.append(f"РћС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ РёРіСЂРѕРєР°: {player}.")
    if pos:
        steps.append(f"РћС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ РѕС„РёС†РёР°Р»СЊРЅСѓСЋ РїРѕР·РёС†РёСЋ: pos{pos}.")
    elif role:
        steps.append(f"РћС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ СЂРѕР»СЊ: {role}.")
    if stage:
        steps.append(f"РћС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ СЃС‚Р°РґРёСЋ: {stage}.")
    if "ti" in q or "РѕС‚РѕР±СЂР°РІ" in q or "РєРІР°Р»РёС„РёС†" in q:
        steps.append("РџСЂРѕРІРµСЂРёС‚СЊ РІРЅРµС€РЅРёР№ РёСЃС‚РѕС‡РЅРёРє РґР»СЏ СЃРѕСЃС‚Р°РІР°/СЃРїРёСЃРєР° TI-РєРІР°Р»РёС„РёС†РёСЂРѕРІР°РЅРЅС‹С… РєРѕРјР°РЅРґ.")
    steps.append(f"Р’РµСЂРЅСѓС‚СЊ РЅРµ Р±РѕР»СЊС€Рµ {limit} СЃС‚СЂРѕРє Рё СЏРІРЅРѕ РЅР°Р·РІР°С‚СЊ РёСЃС‚РѕС‡РЅРёРє РґР°РЅРЅС‹С….")
    return steps


def sql_planner_requested(question: str) -> bool:
    q = normalize_text(question)
    return any(
        token in q
        for token in [
            "sql",
            "planner",
            "query plan",
            "show plan",
            "explain plan",
            "РїР»Р°РЅ Р·Р°РїСЂРѕСЃР°",
            "РїРѕРєР°Р¶Рё РїР»Р°РЅ",
            "РїРѕРєР°Р¶Рё Р·Р°РїСЂРѕСЃ",
            "РєР°Рє Р±СѓРґРµС€СЊ",
        ]
    )


def compact_sql(sql: str | None) -> str | None:
    if sql is None:
        return None
    return re.sub(r"\s+", " ", textwrap.dedent(sql).strip())


def build_sql_plan(question: str, con: sqlite3.Connection | None = None, limit: int | None = None) -> SQLPlan:
    own = con is None
    con = con or connect()
    try:
        q = normalize_text(question)
        max_rows = limit or extract_limit(question)
        pos = extract_position(question)
        role = extract_role_group(question) or position_to_role_group(pos)
        stage = extract_stage_bucket(question)
        team = resolve_team(question, con)
        player = None if team else extract_player(question, con)
        ti_only = ti_filter_requested(question)
        role_slot = extract_role_slot(question)
        filters: dict[str, Any] = {"limit": max_rows, "ti2026_only": ti_only}
        if pos:
            filters["official_position"] = pos
        if role:
            filters["role_group"] = role
        if stage:
            filters["stage_bucket"] = stage
        if team:
            filters["team_name"] = team
        if player:
            filters["official_name"] = player
        if role_slot:
            filters["role_slot"] = role_slot

        if any(token in q for token in ["С„РѕСЂРјСѓР»", "РєР°Рє СЃС‡РёС‚", "scoring", "РѕС‡РєРё СЃС‡РёС‚"]) and not banner_rescoring_requested(question):
            sql = """
                SELECT 'banner_stat' AS row_kind, profile_id, role_scope,
                       CAST(banner_slot AS TEXT) AS item_slot, stat_name AS item_name,
                       multiplier, quality_tier, trait, enabled, notes,
                       NULL AS bonus_pct, NULL AS condition_metric, NULL AS condition_operator, NULL AS condition_value
                FROM analytics_scoring_formula
                UNION ALL
                SELECT 'coach_title' AS row_kind, profile_id, role_scope,
                       title_slot AS item_slot, title_name AS item_name,
                       NULL AS multiplier, NULL AS quality_tier, NULL AS trait, enabled, notes,
                       bonus_pct, condition_metric, condition_operator, condition_value
                FROM analytics_scoring_titles
                ORDER BY row_kind, role_scope, item_slot
            """
            return SQLPlan(
                question=question,
                route="scoring_formula",
                intent="explain fantasy scoring profile",
                tables_or_views=["analytics_scoring_formula", "analytics_scoring_titles", "fantasy_scoring_profile_banners", "fantasy_scoring_profile_stats", "fantasy_scoring_profile_titles"],
                filters=filters,
                metrics=["multiplier", "bonus_pct", "enabled"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if optimizer_v2_requested(question) and any(token in q for token in ["backtest", "quality", "evaluation", "бэктест", "качество"]):
            sql = """
                SELECT entity_type, optimizer_scope, metric_name, metric_scope, metric_value
                FROM analytics_optimizer_v2_evaluation
                ORDER BY entity_type, optimizer_scope, metric_name
            """
            return SQLPlan(
                question=question,
                route="optimizer_v2_backtest",
                intent="evaluate optimizer v2 candidate backtest",
                tables_or_views=["analytics_optimizer_v2_evaluation", "foundation_optimizer_v2_evaluation_reports"],
                filters=filters,
                metrics=["mae", "spearman", "top5_overlap", "ndcg_5", "regret_at_1"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if optimizer_baselines_requested(question):
            sql = """
                SELECT entity_type, optimizer_scope, baseline_id, metric_name, metric_scope, segment_key, metric_value
                FROM analytics_optimizer_foundation_baselines
                ORDER BY entity_type, optimizer_scope, baseline_id, metric_scope, segment_key, metric_name
            """
            return SQLPlan(
                question=question,
                route="optimizer_baselines_foundation",
                intent="compare optimizer against simple baselines",
                tables_or_views=["analytics_optimizer_foundation_baselines", "foundation_optimizer_baseline_reports"],
                filters=filters,
                metrics=["mae", "spearman", "top5_overlap", "ndcg_5", "regret_at_1"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if optimizer_backtest_requested(question):
            sql = """
                SELECT entity_type, optimizer_scope, metric_name, metric_scope, metric_value
                FROM analytics_optimizer_foundation_evaluation
                WHERE metric_scope = 'entity'
                  AND metric_name IN ('mae', 'spearman', 'top3_overlap', 'top5_overlap', 'ndcg_5', 'ndcg_10', 'regret_at_1')
                ORDER BY entity_type, optimizer_scope, metric_name
            """
            return SQLPlan(
                question=question,
                route="optimizer_backtest_foundation",
                intent="evaluate foundation optimizer backtest",
                tables_or_views=["analytics_optimizer_foundation_evaluation", "foundation_optimizer_evaluation_reports"],
                filters=filters,
                metrics=["mae", "spearman", "top3_overlap", "top5_overlap", "ndcg_5", "ndcg_10", "regret_at_1"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if prediction_backtest_requested(question):
            sql = """
                SELECT target_id, split_name, entity_type, chosen_family, chosen_model_id,
                       param_a, param_b, metric_entity_spearman, metric_ndcg_5,
                       metric_top5_overlap, metric_mae, metric_regret_at_1
                FROM analytics_prediction_production_model_choices
                ORDER BY target_id, split_name
            """
            return SQLPlan(
                question=question,
                route="prediction_production_model_choices",
                intent="inspect production prediction champion models",
                tables_or_views=["analytics_prediction_production_model_choices", "production_prediction_model_choices"],
                filters=filters,
                metrics=["metric_entity_spearman", "metric_ndcg_5", "metric_top5_overlap", "metric_mae", "metric_regret_at_1"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if banner_decision_requested(question):
            risk_profile = extract_risk_profile(question)
            if any(token in q for token in ["lineup", "lineups", "лайнап", "состав"]):
                sql = """
                    SELECT risk_profile, lineup_rank,
                           core_team_name, core_players, core_decision_score,
                           mid_team_name, mid_player, mid_decision_score,
                           support_team_name, support_players, support_decision_score,
                           lineup_score_1_100
                    FROM analytics_banner_decision_lineups
                    WHERE decision_scope = ?
                      AND risk_profile = ?
                    ORDER BY lineup_rank
                """
                return SQLPlan(
                    question=question,
                    route="banner_decision_lineups",
                    intent="practical lineup recommendation by risk profile",
                    tables_or_views=["analytics_banner_decision_lineups", "banner_decision_lineups"],
                    filters=filters | {"risk_profile": risk_profile},
                    metrics=["lineup_score_1_100", "core_decision_score", "mid_decision_score", "support_decision_score"],
                    sql=compact_sql(sql),
                    params=["ti2026" if ti_only else "all", risk_profile],
                    confidence="high",
                )
            if role_slot:
                sql = """
                    SELECT risk_profile, role_slot, player_names, team_name,
                           decision_score_1_100, decision_raw
                    FROM analytics_banner_decision_role_slots
                    WHERE decision_scope = ?
                      AND risk_profile = ?
                    ORDER BY role_slot, decision_score_1_100 DESC, decision_raw DESC
                """
                return SQLPlan(
                    question=question,
                    route="banner_decision_role_slots",
                    intent="risk-profile role-slot decision surface",
                    tables_or_views=["analytics_banner_decision_role_slots", "banner_decision_entity_scores"],
                    filters=filters | {"risk_profile": risk_profile},
                    metrics=["decision_score_1_100", "decision_raw"],
                    sql=compact_sql(sql),
                    params=["ti2026" if ti_only else "all", risk_profile],
                    confidence="high",
                )
            sql = """
                SELECT risk_profile, role_group, official_name, team_name, official_position,
                       decision_score_1_100, decision_raw
                FROM analytics_banner_decision_players
                WHERE decision_scope = ?
                  AND risk_profile = ?
                ORDER BY role_group, decision_score_1_100 DESC, decision_raw DESC
            """
            return SQLPlan(
                question=question,
                route="banner_decision_players",
                intent="risk-profile player decision surface",
                tables_or_views=["analytics_banner_decision_players", "banner_decision_entity_scores"],
                filters=filters | {"risk_profile": risk_profile},
                metrics=["decision_score_1_100", "decision_raw"],
                sql=compact_sql(sql),
                params=["ti2026" if ti_only else "all", risk_profile],
                confidence="high",
            )

        if banner_rescoring_requested(question):
            if role_slot:
                sql = """
                    SELECT role_slot, player_names, team_name,
                           rescore_score_1_100, predicted_anchor_score, p90_anchor_score,
                           p_top3_anchor, stability_index, rank_strength_index
                    FROM analytics_banner_rescoring_role_slots
                    WHERE rescoring_scope = ?
                    ORDER BY role_slot, rescore_score_1_100 DESC, rescore_raw DESC
                """
                return SQLPlan(
                    question=question,
                    route="banner_rescoring_role_slots",
                    intent="banner rescoring for role slots",
                    tables_or_views=["analytics_banner_rescoring_role_slots", "banner_rescoring_entity_scores"],
                    filters=filters,
                    metrics=["rescore_score_1_100", "predicted_anchor_score", "p90_anchor_score", "p_top3_anchor"],
                    sql=compact_sql(sql),
                    params=["ti2026" if ti_only else "all"],
                    confidence="high",
                )
            sql = """
                SELECT role_group, official_name, team_name, official_position,
                       rescore_score_1_100, predicted_anchor_score, p90_anchor_score,
                       p_top3_anchor, stability_index, rank_strength_index
                FROM analytics_banner_rescoring_players
                WHERE rescoring_scope = ?
                ORDER BY role_group, rescore_score_1_100 DESC, rescore_raw DESC
            """
            return SQLPlan(
                question=question,
                route="banner_rescoring_players",
                intent="banner rescoring for players",
                tables_or_views=["analytics_banner_rescoring_players", "banner_rescoring_entity_scores"],
                filters=filters,
                metrics=["rescore_score_1_100", "predicted_anchor_score", "p90_anchor_score", "p_top3_anchor"],
                sql=compact_sql(sql),
                params=["ti2026" if ti_only else "all"],
                confidence="high",
            )

        if monte_carlo_requested(question):
            if role_slot:
                target_id = extract_prediction_target(question, "role_slot")
                sql = f"""
                    SELECT target_id, split_name, team_name, role_slot, player_names,
                           predicted_score, simulated_mean_score, simulated_std_score,
                           p_top1, p_top3, p_top5, expected_rank, p90_sim_score
                    FROM analytics_prediction_monte_carlo_role_slots
                    WHERE target_id = '{target_id}'
                      AND split_name = 'temporal_60_40'
                    ORDER BY p_top1 DESC, p_top3 DESC, predicted_score DESC
                    LIMIT {int(max_rows)}
                """
                return SQLPlan(
                    question=question,
                    route="prediction_monte_carlo_role_slots",
                    intent="simulate role-slot ranking stability with Monte Carlo",
                    tables_or_views=["analytics_prediction_monte_carlo_role_slots", "production_monte_carlo_entity_results"],
                    filters=filters | {"target_id": target_id, "split_name": "temporal_60_40"},
                    metrics=["p_top1", "p_top3", "p_top5", "expected_rank", "simulated_std_score"],
                    sql=compact_sql(sql),
                    confidence="medium",
                )
            target_id = extract_prediction_target(question, "player")
            sql = f"""
                SELECT target_id, split_name, team_name, official_name, official_position, role_group,
                       predicted_score, simulated_mean_score, simulated_std_score,
                       p_top1, p_top3, p_top5, expected_rank, p90_sim_score
                FROM analytics_prediction_monte_carlo_players
                WHERE target_id = '{target_id}'
                  AND split_name = 'temporal_60_40'
                ORDER BY p_top1 DESC, p_top3 DESC, predicted_score DESC
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="prediction_monte_carlo_players",
                intent="simulate player ranking stability with Monte Carlo",
                tables_or_views=["analytics_prediction_monte_carlo_players", "production_monte_carlo_entity_results"],
                filters=filters | {"target_id": target_id, "split_name": "temporal_60_40"},
                metrics=["p_top1", "p_top3", "p_top5", "expected_rank", "simulated_std_score"],
                sql=compact_sql(sql),
                confidence="medium",
            )

        if prediction_requested(question):
            if role_slot:
                target_id = extract_prediction_target(question, "role_slot")
                sql = f"""
                    SELECT chosen_family, chosen_model_id, target_id, split_name,
                           team_name, role_slot, player_names, predicted_score,
                           q25, q50, q75, q90, maps_observed, train_rows_used
                    FROM analytics_prediction_production_role_slots
                    WHERE target_id = '{target_id}'
                      AND split_name = 'temporal_60_40'
                    ORDER BY predicted_score DESC
                    LIMIT {int(max_rows)}
                """
                return SQLPlan(
                    question=question,
                    route="prediction_production_role_slots",
                    intent="rank role-slots with production prediction surface",
                    tables_or_views=["analytics_prediction_production_role_slots", "production_prediction_entity_scores"],
                    filters=filters | {"target_id": target_id, "split_name": "temporal_60_40"},
                    metrics=["predicted_score", "q75", "metric_entity_spearman", "metric_ndcg_5"],
                    sql=compact_sql(sql),
                    confidence="medium",
                )
            target_id = extract_prediction_target(question, "player")
            sql = f"""
                SELECT chosen_family, chosen_model_id, target_id, split_name,
                       official_name, team_name, official_position, role_group, predicted_score,
                       q25, q50, q75, q90, maps_observed, train_rows_used
                FROM analytics_prediction_production_players
                WHERE target_id = '{target_id}'
                  AND split_name = 'temporal_60_40'
                ORDER BY predicted_score DESC
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="prediction_production_players",
                intent="rank players with production prediction surface",
                tables_or_views=["analytics_prediction_production_players", "production_prediction_entity_scores"],
                filters=filters | {"target_id": target_id, "split_name": "temporal_60_40"},
                metrics=["predicted_score", "q75", "metric_entity_spearman", "metric_ndcg_5"],
                sql=compact_sql(sql),
                confidence="medium",
            )

        if any(token in q for token in ["metric", "метрик", "что значит", "как считается", "definition", "объясни показатель", "объясни метрику"]) and not optimizer_requested(question):
            sql = """
                SELECT metric_name, layer_name, entity_scope, short_definition,
                       calculation_summary, interpretation, caveats
                FROM analytics_metric_definitions
                ORDER BY layer_name, metric_name, entity_scope
            """
            return SQLPlan(
                question=question,
                route="metric_definitions",
                intent="explain stored metric definitions",
                tables_or_views=["analytics_metric_definitions", "metric_definitions"],
                filters=filters,
                metrics=["metric_name", "layer_name", "entity_scope"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if any(token in q for token in ["backtest", "Р±СЌРєС‚РµСЃС‚", "РєР°С‡РµСЃС‚РІРѕ РјРѕРґРµР»Рё", "РїСЂРѕРІРµСЂРєР° РјРѕРґРµР»Рё"]):
            sql = """
                SELECT entity_type, segment_key, COUNT(*) AS rows_backtested,
                       AVG(abs_error) AS mae,
                       MIN(actual_test_score) AS min_actual_score,
                       AVG(actual_test_score) AS avg_actual_score,
                       MAX(actual_test_score) AS max_actual_score,
                       AVG(predicted_score) AS avg_predicted_score
                FROM analytics_reliability_foundation_backtest
                GROUP BY entity_type, segment_key
                ORDER BY entity_type, segment_key
            """
            return SQLPlan(
                question=question,
                route="reliability_backtest_foundation",
                intent="evaluate foundation reliability backtest",
                tables_or_views=["analytics_reliability_foundation_backtest"],
                filters=filters,
                metrics=["rows_backtested", "mae", "avg_actual_score", "avg_predicted_score"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if any(token in q for token in ["source cache", "external_source", "РєСЌС€", "РёСЃС‚РѕС‡РЅРёРєРё РІ Р±Р°Р·Рµ"]):
            sql = """
                SELECT source_key, source_name, source_url, fetched_at_utc,
                       status, content_type, http_status, notes
                FROM analytics_sources
                ORDER BY fetched_at_utc DESC
            """
            return SQLPlan(
                question=question,
                route="source_cache_status",
                intent="inspect cached external sources",
                tables_or_views=["analytics_sources", "external_source_cache"],
                filters=filters,
                metrics=["status", "http_status"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if (
            ti_only
            and any(token in q for token in ["РєРѕРјР°РЅРґ", "teams", "СЃРїРёСЃРѕРє", "СѓС‡Р°СЃС‚РЅРёРє"])
            and not optimizer_requested(question)
            and not any(token in q for token in ["С‚РѕРї", "top", "Р»СѓС‡С€РёРµ", "С„РµРЅС‚РµР·Рё", "С„СЌРЅС‚РµР·Рё", "fantasy", "РѕС‡Рє"])
        ):
            sql = """
                SELECT team_name, source_team_name, qualification_path, region,
                       roster_text, has_ewc_player_data, source_url, secondary_source_url,
                       checked_at_utc, confidence_label
                FROM analytics_ti2026_teams
                ORDER BY has_ewc_player_data DESC, qualification_path, team_name
            """
            return SQLPlan(
                question=question,
                route="ti_qualified_teams",
                intent="list TI 2026 qualified teams from source cache",
                tables_or_views=["analytics_ti2026_teams", "ti_qualified_teams"],
                filters=filters,
                metrics=["has_ewc_player_data", "confidence_label"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if optimizer_requested(question):
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            if role_slot or pair_requested:
                view = "analytics_optimizer_role_slots_foundation"
                clauses: list[str] = ["optimizer_scope = ?"]
                params: list[Any] = ["ti2026" if ti_only else "all"]
                if ti_only:
                    clauses.append("ti2026_qualified = 1")
                if role_slot:
                    clauses.append("role_slot = ?")
                    params.append(role_slot)
                if team:
                    clauses.append("team_name = ?")
                    params.append(team)
                where = "WHERE " + " AND ".join(clauses) if clauses else ""
                sql = f"""
                    SELECT optimizer_score_1_100, team_name, role_slot, player_names,
                           optimizer_raw_score AS predicted_score_raw,
                           expected_estimate, high_estimate, low_estimate,
                           reliability_score_1_100, map_p75_score, series_mean_p75, series_top1_p75,
                           stat_balance_score, volatility_ratio, sample_weight,
                           ti2026_qualified, qualification_path, ti_region,
                           data_quality_label, recommendation_note
                    FROM {view}
                    {where}
                    ORDER BY role_slot, optimizer_score_1_100 DESC, optimizer_raw_score DESC
                    LIMIT {int(max_rows)}
                """
                return SQLPlan(
                    question=question,
                    route="banner_optimizer_role_slots_foundation",
                    intent="rank fantasy role-slot picks by foundation optimizer score",
                    tables_or_views=[view, "foundation_optimizer_recommendations"],
                    filters=filters,
                    metrics=["optimizer_score_1_100", "predicted_score_raw", "reliability_score_1_100", "series_top1_p75"],
                    sql=compact_sql(sql),
                    params=params,
                    confidence="high",
                )

            view = "analytics_optimizer_players_foundation"
            clauses = ["optimizer_scope = ?"]
            params = ["ti2026" if ti_only else "all"]
            if ti_only:
                clauses.append("ti2026_qualified = 1")
            if pos:
                clauses.append("official_position = ?")
                params.append(pos)
            if role:
                clauses.append("role_group = ?")
                params.append(role)
            if team:
                clauses.append("team_name = ?")
                params.append(team)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            sql = f"""
                SELECT optimizer_score_1_100, official_name, team_name,
                       official_position, role_group, optimizer_raw_score AS predicted_score_raw,
                       expected_estimate, high_estimate, low_estimate,
                       reliability_score_1_100, map_p75_score, series_mean_p75, series_top1_p75,
                       stat_balance_score, volatility_ratio, sample_weight,
                       ti2026_qualified, qualification_path, ti_region,
                       data_quality_label, recommendation_note
                FROM {view}
                {where}
                ORDER BY role_group, optimizer_score_1_100 DESC, optimizer_raw_score DESC
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="banner_optimizer_players_foundation",
                intent="rank fantasy player picks by foundation optimizer score",
                tables_or_views=[view, "foundation_optimizer_recommendations"],
                filters=filters,
                metrics=["optimizer_score_1_100", "predicted_score_raw", "reliability_score_1_100", "series_top1_p75"],
                sql=compact_sql(sql),
                params=params,
                confidence="high",
            )

        reliability_tokens = ["надеж", "надёж", "стабил", "риск", "reliable", "stable", "risk"]
        if any(token in q for token in reliability_tokens):
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            if role_slot or pair_requested:
                view = "analytics_reliable_role_slots_foundation"
                clauses = []
                params = []
                if ti_only:
                    clauses.append("ti2026_qualified = 1")
                if role_slot:
                    clauses.append("role_slot = ?")
                    params.append(role_slot)
                if team:
                    clauses.append("team_name = ?")
                    params.append(team)
                where = "WHERE " + " AND ".join(clauses) if clauses else ""
                sql = f"""
                    SELECT reliability_score_1_100, team_name, role_slot, player_names,
                           reliability_raw_score AS predicted_score_raw,
                           low_estimate, expected_estimate, high_estimate,
                           confidence_label,
                           sample_maps, sample_series AS train_series_seen,
                           map_p75_score, series_mean_p75, series_top1_p75,
                           volatility_ratio, stat_balance_score, data_quality_label
                    FROM {view}
                    {where}
                    ORDER BY role_slot, reliability_score_1_100 DESC, reliability_raw_score DESC
                    LIMIT {int(max_rows)}
                """
                return SQLPlan(
                    question=question,
                    route="reliable_role_slots_foundation",
                    intent="rank reliable fantasy role-slot picks with foundation intervals",
                    tables_or_views=[view, "foundation_reliability_entity_scores"],
                    filters=filters,
                    metrics=["reliability_score_1_100", "low_estimate", "expected_estimate", "high_estimate"],
                    sql=compact_sql(sql),
                    params=params,
                    confidence="high",
                )

            view = "analytics_reliable_players_foundation"
            clauses = []
            params = []
            if ti_only:
                clauses.append("ti2026_qualified = 1")
            if pos:
                clauses.append("official_position = ?")
                params.append(pos)
            if role:
                clauses.append("role_group = ?")
                params.append(role)
            if team:
                clauses.append("team_name = ?")
                params.append(team)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            sql = f"""
                SELECT reliability_score_1_100, official_name, team_name,
                       official_position, role_group, reliability_raw_score AS predicted_score_raw,
                       low_estimate, expected_estimate, high_estimate,
                       confidence_label,
                       sample_maps, sample_series AS train_series_seen,
                       map_p75_score, series_mean_p75, series_top1_p75,
                       volatility_ratio, stat_balance_score, data_quality_label
                FROM {view}
                {where}
                ORDER BY reliability_score_1_100 DESC, reliability_raw_score DESC
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="reliable_players_foundation",
                intent="rank reliable fantasy player picks with foundation intervals",
                tables_or_views=[view, "foundation_reliability_entity_scores"],
                filters=filters,
                metrics=["reliability_score_1_100", "low_estimate", "expected_estimate", "high_estimate"],
                sql=compact_sql(sql),
                params=params,
                confidence="high",
            )

        if any(token in q for token in ["СЃРѕСЃС‚Р°РІ", "roster", "РёРіСЂРѕРєРё РєРѕРјР°РЅРґС‹"]) and team:
            sql = """
                SELECT team_name, official_position, role_group, official_name,
                       db_player_name, account_id, source_name, source_url
                FROM analytics_rosters
                WHERE team_name = ?
                ORDER BY official_position
            """
            return SQLPlan(
                question=question,
                route="roster",
                intent="show official team roster",
                tables_or_views=["analytics_rosters", "player_identity_registry", "liquipedia_team_rosters"],
                filters=filters,
                metrics=["official_position", "official_name"],
                sql=compact_sql(sql),
                params=[team],
                confidence="high",
            )

        if any(token in q for token in ["avg core", "core + mid", "role-category", "СЂРѕР»СЊ", "СЃР»РѕС‚ РєРѕРјР°РЅРґС‹"]):
            clauses = []
            params = []
            if team:
                clauses.append("team_name = ?")
                params.append(team)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            sql = f"""
                SELECT match_date, stage_name, team_name, opponent_name,
                       avg_core_fantasy_score, mid_fantasy_score,
                       avg_support_fantasy_score, team_role_fantasy_score,
                       core_players, mid_player, support_players
                FROM analytics_team_role_maps
                {where}
                ORDER BY match_date, team_name
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="role_map_summary",
                intent="show per-map role-category fantasy summary",
                tables_or_views=["analytics_team_role_maps", "fantasy_team_role_map_scores"],
                filters=filters,
                metrics=["avg_core_fantasy_score", "mid_fantasy_score", "avg_support_fantasy_score"],
                sql=compact_sql(sql),
                params=params,
                confidence="high",
            )

        if any(token in q for token in ["РєР°СЂС‚С‹ РёРіСЂРѕРєР°", "РїРѕ РєР°Р¶РґРѕР№ РєР°СЂС‚Рµ", "РїРѕ РјР°С‚С‡Р°Рј РёРіСЂРѕРєР°"]) and player:
            sql = """
                SELECT fantasy_score, match_date, stage_name, team_name, opponent_name,
                       official_name, official_position, hero_name, match_id,
                       won, duration_sec, base_points_total, profile_bonus_points, title_bonus_points
                FROM analytics_player_maps
                WHERE official_name = ?
                ORDER BY match_date, match_id
                LIMIT ?
            """
            return SQLPlan(
                question=question,
                route="player_maps",
                intent="show all fantasy map rows for one player",
                tables_or_views=["analytics_player_maps", "fantasy_player_map_scores"],
                filters=filters,
                metrics=["fantasy_score", "base_points_total", "profile_bonus_points", "title_bonus_points"],
                sql=compact_sql(sql),
                params=[player, max_rows],
                confidence="high",
            )

        if any(token in q for token in ["С‚РѕРї", "top", "Р»СѓС‡С€РёРµ"]) and any(
            token in q for token in ["С„РµРЅС‚РµР·Рё", "С„СЌРЅС‚РµР·Рё", "fantasy", "РѕС‡Рє"]
        ):
            view = "analytics_player_maps"
            clauses = []
            params = []
            if ti_only:
                clauses.append("ti2026_qualified = 1")
            if pos:
                clauses.append("official_position = ?")
                params.append(pos)
            if role:
                clauses.append("role_group = ?")
                params.append(role)
            if team:
                clauses.append("team_name = ?")
                params.append(team)
            if stage:
                clauses.append("stage_bucket = ?")
                params.append(stage)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            sql = f"""
                SELECT fantasy_score, official_name, team_name, official_position,
                       role_group, hero_name, match_id, match_date, stage_name,
                       opponent_name, won, duration_sec, qualification_path, ti_region
                FROM {view}
                {where}
                ORDER BY fantasy_score DESC
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="top_fantasy_maps",
                intent="rank individual player-map fantasy scores",
                tables_or_views=[view, "fantasy_player_map_scores", "player_identity_registry"],
                filters=filters,
                metrics=["fantasy_score"],
                sql=compact_sql(sql),
                params=params,
                confidence="high",
            )

        missing_external: list[str] = []
        if needs_web_source(question):
            missing_external.append("Question mentions external facts; verify via source_urls/fetch before SQL filtering.")
        return SQLPlan(
            question=question,
            route="fallback_db_status" if not missing_external else "source_urls",
            intent="uncertain; inspect DB status or external source candidates",
            tables_or_views=["db_status"] if not missing_external else ["analytics_sources"],
            filters=filters,
            metrics=[],
            sql=None,
            missing_external_facts=missing_external,
            confidence="low",
            notes=["No precise SQL template matched this question."],
        )
    finally:
        if own:
            con.close()


def explain_sql_plan(question: str, con: sqlite3.Connection | None = None, limit: int | None = None) -> pd.DataFrame:
    plan = build_sql_plan(question, con=con, limit=limit)
    rows = [
        {"key": "route", "value": plan.route},
        {"key": "intent", "value": plan.intent},
        {"key": "confidence", "value": plan.confidence},
        {"key": "tables_or_views", "value": ", ".join(plan.tables_or_views)},
        {"key": "filters", "value": json.dumps(plan.filters, ensure_ascii=False, sort_keys=True)},
        {"key": "metrics", "value": ", ".join(plan.metrics)},
        {"key": "params", "value": json.dumps(plan.params, ensure_ascii=False)},
        {"key": "missing_external_facts", "value": "; ".join(plan.missing_external_facts)},
        {"key": "notes", "value": "; ".join(plan.notes)},
        {"key": "sql", "value": plan.sql or ""},
    ]
    return pd.DataFrame(rows)


def db_status(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        objects = [
            "matches",
            "player_identity_registry",
            "analytics_player_maps",
            "analytics_team_role_maps",
            "dota_heroes",
            "analytics_sources",
            "analytics_ti2026_teams",
            "analytics_reliable_players_foundation",
            "analytics_reliable_role_slots_foundation",
            "analytics_reliability_foundation_backtest",
            "analytics_optimizer_players",
            "analytics_optimizer_role_slots",
            "analytics_db_objects",
        ]
        rows = []
        for name in objects:
            exists = table_exists(con, name)
            count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] if exists else None
            rows.append({"object": name, "exists": exists, "rows": count})
        return pd.DataFrame(rows)
    finally:
        if own:
            con.close()


def roster(team: str, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        team_name = resolve_team(team, con) or team
        return run_sql(
            """
            SELECT team_name, official_position, role_group, official_name,
                   db_player_name, account_id, source_name, source_url
            FROM analytics_rosters
            WHERE team_name = ?
            ORDER BY official_position
            """,
            (team_name,),
            con,
        )
    finally:
        if own:
            con.close()


def reliable_players_foundation(
    *,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    ti2026_only: bool = False,
    limit: int = 15,
    include_support: bool | None = None,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        if include_support is None:
            include_support = True
        view = "analytics_reliable_players_foundation"
        clauses = []
        params: list[Any] = []
        if not include_support:
            clauses.append("role_group <> 'support'")
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return run_sql(
            f"""
            SELECT reliability_score_1_100, official_name, team_name,
                   official_position, role_group,
                   reliability_raw_score AS predicted_score_raw,
                   low_estimate, expected_estimate, high_estimate,
                   confidence_label,
                   sample_maps, sample_series AS train_series_seen,
                   map_mean_score, map_p75_score, map_p90_score,
                   series_mean_avg, series_mean_p75,
                   series_top1_avg, series_top1_p75, series_top1_p90,
                   recent_map_mean_5, recent_series_mean_3, recent_series_top1_3,
                   team_segment_strength, positive_stat_count,
                   top_stat_share, stat_balance_score, volatility_ratio,
                   sample_weight, data_quality_label
            FROM {view}
            {where}
            ORDER BY reliability_score_1_100 DESC, reliability_raw_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def reliable_players_v2(
    *,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    ti2026_only: bool = False,
    limit: int = 15,
    include_support: bool | None = None,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    # Compatibility alias. New code should call reliable_players_foundation(...).
    return reliable_players_foundation(
        position=position,
        role_group=role_group,
        team=team,
        ti2026_only=ti2026_only,
        limit=limit,
        include_support=include_support,
        con=con,
    )


def reliable_role_slots_foundation(
    *,
    role_slot: str | None = None,
    team: str | None = None,
    ti2026_only: bool = False,
    limit: int = 15,
    include_support: bool | None = None,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        if include_support is None:
            include_support = True
        view = "analytics_reliable_role_slots_foundation"
        clauses = []
        params: list[Any] = []
        if not include_support:
            clauses.append("role_slot <> 'support_pair'")
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return run_sql(
            f"""
            SELECT reliability_score_1_100, team_name, role_slot, player_names,
                   reliability_raw_score AS predicted_score_raw,
                   low_estimate, expected_estimate, high_estimate,
                   confidence_label,
                   sample_maps, sample_series AS train_series_seen,
                   map_mean_score, map_p75_score, map_p90_score,
                   series_mean_avg, series_mean_p75,
                   series_top1_avg, series_top1_p75, series_top1_p90,
                   recent_map_mean_5, recent_series_mean_3, recent_series_top1_3,
                   team_segment_strength, positive_stat_count,
                   top_stat_share, stat_balance_score, volatility_ratio,
                   sample_weight, data_quality_label
            FROM {view}
            {where}
            ORDER BY role_slot, reliability_score_1_100 DESC, reliability_raw_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def reliable_role_slots_v2(
    *,
    role_slot: str | None = None,
    team: str | None = None,
    ti2026_only: bool = False,
    limit: int = 15,
    include_support: bool | None = None,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    # Compatibility alias. New code should call reliable_role_slots_foundation(...).
    return reliable_role_slots_foundation(
        role_slot=role_slot,
        team=team,
        ti2026_only=ti2026_only,
        limit=limit,
        include_support=include_support,
        con=con,
    )


def reliability_backtest_foundation(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT entity_type, segment_key, COUNT(*) AS rows_backtested,
               AVG(abs_error) AS mae,
               MIN(actual_test_score) AS min_actual_score,
               AVG(actual_test_score) AS avg_actual_score,
               MAX(actual_test_score) AS max_actual_score,
               AVG(predicted_score) AS avg_predicted_score
        FROM analytics_reliability_foundation_backtest
        GROUP BY entity_type, segment_key
        ORDER BY entity_type, segment_key
        """,
        con=con,
    )


def reliability_backtest_v2(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    # Compatibility alias. New code should call reliability_backtest_foundation(...).
    return reliability_backtest_foundation(con=con)


def ti_qualified_teams(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT team_name, source_team_name, qualification_path, region,
               roster_text, has_ewc_player_data, source_url, secondary_source_url,
               checked_at_utc, confidence_label
        FROM analytics_ti2026_teams
        ORDER BY has_ewc_player_data DESC, qualification_path, team_name
        """,
        con=con,
    )


def source_cache_status(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT source_key, source_name, source_url, fetched_at_utc,
               status, content_type, http_status, notes
        FROM analytics_sources
        ORDER BY fetched_at_utc DESC
        """,
        con=con,
    )


def metric_definitions(metric_name: str | None = None, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        if metric_name:
            return run_sql(
                """
                SELECT metric_name, layer_name, entity_scope, short_definition,
                       calculation_summary, interpretation, caveats
                FROM analytics_metric_definitions
                WHERE metric_name = ?
                ORDER BY layer_name, entity_scope
                """,
                (metric_name,),
                con,
            )
        return run_sql(
            """
            SELECT metric_name, layer_name, entity_scope, short_definition,
                   calculation_summary, interpretation, caveats
            FROM analytics_metric_definitions
            ORDER BY layer_name, metric_name, entity_scope
            """,
            con=con,
        )
    finally:
        if own:
            con.close()


def optimizer_backtest_foundation(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT entity_type, optimizer_scope, metric_name, metric_scope, metric_value
        FROM analytics_optimizer_foundation_evaluation
        WHERE metric_scope = 'entity'
          AND metric_name IN ('mae', 'spearman', 'top3_overlap', 'top5_overlap', 'ndcg_5', 'ndcg_10', 'regret_at_1')
        ORDER BY entity_type, optimizer_scope, metric_name
        """,
        con=con,
    )


def optimizer_baselines_foundation(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT entity_type, optimizer_scope, baseline_id, metric_name, metric_scope, segment_key, metric_value
        FROM analytics_optimizer_foundation_baselines
        ORDER BY entity_type, optimizer_scope, baseline_id, metric_scope, segment_key, metric_name
        """,
        con=con,
    )


def optimizer_v2_players(
    *,
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["optimizer_scope = ?"]
        params: list[Any] = ["ti2026" if ti2026_only else "all"]
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT optimizer_v2_score_1_100, official_name, team_name, official_position, role_group,
                   optimizer_v2_raw_score, series_top1_p75, series_mean_p75, map_p75_score,
                   top_stat_share, volatility_ratio, sample_weight, recommendation_note
            FROM analytics_optimizer_v2_players
            {where}
            ORDER BY role_group, optimizer_v2_score_1_100 DESC, optimizer_v2_raw_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def optimizer_v2_role_slots(
    *,
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["optimizer_scope = ?"]
        params: list[Any] = ["ti2026" if ti2026_only else "all"]
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT optimizer_v2_score_1_100, team_name, role_slot, player_names,
                   optimizer_v2_raw_score, series_top1_p75, series_mean_p75, map_p75_score,
                   top_stat_share, volatility_ratio, sample_weight, recommendation_note
            FROM analytics_optimizer_v2_role_slots
            {where}
            ORDER BY role_slot, optimizer_v2_score_1_100 DESC, optimizer_v2_raw_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def optimizer_v2_backtest(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT entity_type, optimizer_scope, metric_name, metric_scope, metric_value
        FROM analytics_optimizer_v2_evaluation
        ORDER BY entity_type, optimizer_scope, metric_name
        """,
        con=con,
    )


def banner_optimizer_players_v2(
    *,
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    df = optimizer_v2_players(
        ti2026_only=ti2026_only,
        position=position,
        role_group=role_group,
        team=team,
        limit=limit,
        con=con,
    ).copy()
    if df.empty:
        return df
    return df.rename(
        columns={
            "optimizer_v2_score_1_100": "optimizer_score_1_100",
            "optimizer_v2_raw_score": "predicted_score_raw",
        }
    )


def banner_optimizer_role_slots_v2(
    *,
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    df = optimizer_v2_role_slots(
        ti2026_only=ti2026_only,
        role_slot=role_slot,
        team=team,
        limit=limit,
        con=con,
    ).copy()
    if df.empty:
        return df
    return df.rename(
        columns={
            "optimizer_v2_score_1_100": "optimizer_score_1_100",
            "optimizer_v2_raw_score": "predicted_score_raw",
        }
    )


def banner_optimizer_players_foundation(
    *,
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        view = "analytics_optimizer_players_foundation"
        clauses = []
        params: list[Any] = []
        clauses.append("optimizer_scope = ?")
        params.append("ti2026" if ti2026_only else "all")
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return run_sql(
            f"""
            SELECT optimizer_score_1_100, official_name, team_name,
                   official_position, role_group, optimizer_raw_score AS predicted_score_raw,
                   expected_estimate, high_estimate, low_estimate,
                   reliability_score_1_100, map_p75_score, series_mean_p75, series_top1_p75,
                   stat_balance_score, volatility_ratio, sample_weight,
                   confidence_label, data_quality_label, recommendation_note
            FROM {view}
            {where}
            ORDER BY role_group, optimizer_score_1_100 DESC, optimizer_raw_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_optimizer_players(
    *,
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    # Compatibility alias. Default project optimizer now points to optimizer_v2.
    return banner_optimizer_players_v2(
        ti2026_only=ti2026_only,
        position=position,
        role_group=role_group,
        team=team,
        limit=limit,
        con=con,
    )


def banner_optimizer_role_slots_foundation(
    *,
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        view = "analytics_optimizer_role_slots_foundation"
        clauses = []
        params: list[Any] = []
        clauses.append("optimizer_scope = ?")
        params.append("ti2026" if ti2026_only else "all")
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return run_sql(
            f"""
            SELECT optimizer_score_1_100, team_name, role_slot, player_names,
                   optimizer_raw_score AS predicted_score_raw,
                   expected_estimate, high_estimate, low_estimate,
                   reliability_score_1_100, map_p75_score, series_mean_p75, series_top1_p75,
                   stat_balance_score, volatility_ratio, sample_weight,
                   confidence_label, data_quality_label, recommendation_note
            FROM {view}
            {where}
            ORDER BY role_slot, optimizer_score_1_100 DESC, optimizer_raw_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_optimizer_role_slots(
    *,
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    # Compatibility alias. Default project optimizer now points to optimizer_v2.
    return banner_optimizer_role_slots_v2(
        ti2026_only=ti2026_only,
        role_slot=role_slot,
        team=team,
        limit=limit,
        con=con,
    )


def top_fantasy_maps(
    *,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    stage_bucket: str | None = None,
    ti2026_only: bool = False,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        view = "analytics_player_maps"
        clauses = []
        params: list[Any] = []
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        if stage_bucket:
            clauses.append("stage_bucket = ?")
            params.append(stage_bucket)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return run_sql(
            f"""
            SELECT fantasy_score, official_name, team_name, official_position,
                   role_group, hero_name, match_id, match_date, stage_name,
                   opponent_name, won, duration_sec, qualification_path, ti_region
            FROM {view}
            {where}
            ORDER BY fantasy_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def player_maps(player: str, limit: int = 50, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        name = extract_player(player, con) or player
        return run_sql(
            """
            SELECT fantasy_score, match_date, stage_name, team_name, opponent_name,
                   official_name, official_position, hero_name, match_id,
                   won, duration_sec, base_points_total, profile_bonus_points, title_bonus_points
            FROM analytics_player_maps
            WHERE official_name = ?
            ORDER BY match_date, match_id
            LIMIT ?
            """,
            (name, int(limit)),
            con,
        )
    finally:
        if own:
            con.close()


def role_map_summary(team: str | None = None, limit: int = 30, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = []
        params: list[Any] = []
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return run_sql(
            f"""
            SELECT match_date, stage_name, team_name, opponent_name,
                   avg_core_fantasy_score, mid_fantasy_score,
                   avg_support_fantasy_score, team_role_fantasy_score,
                   core_players, mid_player, support_players
            FROM analytics_team_role_maps
            {where}
            ORDER BY match_date, team_name
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def scoring_formula(profile_id: str | None = None, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        if profile_id is None:
            return run_sql(
                """
                SELECT 'banner_stat' AS row_kind, profile_id, role_scope,
                       CAST(banner_slot AS TEXT) AS item_slot, stat_name AS item_name,
                       multiplier, quality_tier, trait, enabled, notes,
                       NULL AS bonus_pct, NULL AS condition_metric, NULL AS condition_operator, NULL AS condition_value
                FROM analytics_scoring_formula
                UNION ALL
                SELECT 'coach_title' AS row_kind, profile_id, role_scope,
                       title_slot AS item_slot, title_name AS item_name,
                       NULL AS multiplier, NULL AS quality_tier, NULL AS trait, enabled, notes,
                       bonus_pct, condition_metric, condition_operator, condition_value
                FROM analytics_scoring_titles
                ORDER BY row_kind, role_scope, item_slot
                """,
                con=con,
            )
        return run_sql(
            """
            SELECT 'banner_stat' AS row_kind, b.profile_id, b.role_scope,
                   CAST(b.banner_slot AS TEXT) AS item_slot, b.stat_name AS item_name,
                   b.multiplier, b.quality_tier, b.trait, s.enabled, s.notes,
                   NULL AS bonus_pct, NULL AS condition_metric, NULL AS condition_operator, NULL AS condition_value
            FROM fantasy_scoring_profile_banners b
            LEFT JOIN fantasy_scoring_profile_stats s
              ON s.profile_id = b.profile_id
             AND s.role_scope = b.role_scope
             AND s.stat_name = b.stat_name
            WHERE b.profile_id = ?
            UNION ALL
            SELECT 'coach_title' AS row_kind, t.profile_id, t.role_scope,
                   t.title_slot AS item_slot, t.title_name AS item_name,
                   NULL AS multiplier, NULL AS quality_tier, NULL AS trait, t.enabled, t.notes,
                   t.bonus_pct, t.condition_metric, t.condition_operator, t.condition_value
            FROM fantasy_scoring_profile_titles t
            WHERE t.profile_id = ?
            ORDER BY row_kind, role_scope, item_slot
            """,
            (profile_id, profile_id),
            con,
        )
    finally:
        if own:
            con.close()


def source_urls(question: str, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        team = resolve_team(question, con)
        player = extract_player(question, con)
    finally:
        if own:
            con.close()
    query = question
    liquipedia_query = team or player or query
    rows = [
        {
            "source": "Liquipedia",
            "url": "https://liquipedia.net/dota2/Special:Search?"
            + urllib.parse.urlencode({"search": liquipedia_query}),
            "best_for": "rosters, tournament stages, participants, TI qualification context",
        },
        {
            "source": "Dotabuff",
            "url": "https://www.dotabuff.com/esports/leagues/19785",
            "best_for": "EWC 2026 match pages, player nick/position evidence per map",
        },
        {
            "source": "OpenDota",
            "url": "https://api.opendota.com/api/explorer",
            "best_for": "raw match/player statistics if match_id is known",
        },
    ]
    return pd.DataFrame(rows)


def fetch_url_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EWC2026FactAgent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(200_000)
    text = raw.decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", text).strip()


def needs_web_source(question: str) -> bool:
    q = normalize_text(question)
    tokens = [
        "РёРЅС‚РµСЂРЅРµС‚",
        "СЃР°Р№С‚",
        "РёСЃС‚РѕС‡РЅРёРє",
        "liquipedia",
        "Р»РёРєРІРёРїРµРґ",
        "dotabuff",
        "РґРѕС‚Р°Р±Р°С„С„",
        "opendota",
        "ti 2026",
        "the international",
        "РѕС‚РѕР±СЂР°РІ",
        "РєРІР°Р»РёС„РёС†",
    ]
    return any(token in q for token in tokens)


def optimizer_backtest_requested(question: str) -> bool:
    q = normalize_text(question)
    direct_tokens = [
        "optimizer backtest",
        "backtest optimizer",
        "optimizer quality",
        "optimizer evaluation",
        "quality of optimizer",
        "качество оптимизатора",
        "оценка оптимизатора",
        "оптимизатор бэктест",
        "оптимизатор бек",
    ]
    if any(token in q for token in direct_tokens):
        return True
    return optimizer_requested(question) and any(
        token in q for token in ["backtest", "бэктест", "бек", "quality", "evaluation", "метрики качества"]
    )


def optimizer_baselines_requested(question: str) -> bool:
    q = normalize_text(question)
    direct_tokens = [
        "optimizer baselines",
        "optimizer baseline",
        "baseline optimizer",
        "сравнение с бейзлайнами",
        "сравнение с baseline",
        "базовые модели оптимизатора",
        "baseline comparison",
    ]
    return any(token in q for token in direct_tokens)


def optimizer_v2_requested(question: str) -> bool:
    q = normalize_text(question)
    direct_tokens = [
        "optimizer v2",
        "optimizer-v2",
        "v2 optimizer",
        "оптимизатор v2",
        "optimizer candidate",
        "v2 candidate",
        "candidate optimizer",
    ]
    return any(token in q for token in direct_tokens)


def optimizer_foundation_requested(question: str) -> bool:
    q = question.lower()
    return any(
        token in q
        for token in [
            "optimizer foundation",
            "foundation optimizer",
            "legacy optimizer",
            "старый оптимизатор",
            "оптимизатор foundation",
            "foundation-first optimizer",
        ]
    )


def prediction_requested(question: str) -> bool:
    q = normalize_text(question)
    tokens = [
        "prediction",
        "predict",
        "predictive",
        "production prediction",
        "production ranking",
        "model ranking",
        "model score",
        "прогноз",
        "предсказ",
        "модельный рейтинг",
        "production surface",
    ]
    return any(token in q for token in tokens)


def prediction_backtest_requested(question: str) -> bool:
    q = normalize_text(question)
    return prediction_requested(question) and any(
        token in q for token in ["backtest", "evaluation", "quality", "compare", "comparison", "бэктест", "сравн", "качество"]
    )


def monte_carlo_requested(question: str) -> bool:
    q = normalize_text(question)
    return any(
        token in q
        for token in [
            "monte carlo",
            "simulation",
            "simulate",
            "симуляц",
            "монте карло",
            "вероятность топ",
            "p_top1",
            "p_top3",
        ]
    )


def banner_rescoring_requested(question: str) -> bool:
    q = normalize_text(question)
    return any(
        token in q
        for token in [
            "banner rescoring",
            "rescoring",
            "rescore",
            "пересчет баннера",
            "пересчёт баннера",
            "переоценка баннера",
            "banner re-scoring",
        ]
    )


def banner_decision_requested(question: str) -> bool:
    q = normalize_text(question)
    return any(
        token in q
        for token in [
            "banner decision",
            "decision layer",
            "risk profile",
            "lineup",
            "lineups",
            "агрессив",
            "консерват",
            "balanced",
            "aggressive",
            "conservative",
            "составь лайнап",
            "составь lineup",
            "готовый лайнап",
            "готовый lineup",
        ]
    )


def extract_risk_profile(question: str) -> str:
    q = normalize_text(question)
    if any(token in q for token in ["aggressive", "агрессив", "рискованный", "high risk"]):
        return "aggressive"
    if any(token in q for token in ["conservative", "консерват", "safe", "надежный", "надёжный"]):
        return "conservative"
    return "balanced"


def extract_prediction_target(question: str, entity_type: str) -> str:
    q = normalize_text(question)
    prefix = "player" if entity_type == "player" else "role_slot"
    if any(token in q for token in ["map", "карта", "по карте", "single map"]):
        return f"{prefix}_map_score"
    if any(token in q for token in ["mean", "average", "средн", "усред", "стабильн"]):
        return f"{prefix}_series_mean"
    return f"{prefix}_series_top1"


def production_prediction_model_choices(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT target_id, split_name, entity_type, chosen_family, chosen_model_id,
               param_a, param_b, metric_entity_spearman, metric_ndcg_5,
               metric_top5_overlap, metric_mae, metric_regret_at_1
        FROM analytics_prediction_production_model_choices
        ORDER BY target_id, split_name
        """,
        con=con,
    )


def production_prediction_players(
    *,
    target_id: str = "player_series_top1",
    split_name: str = "temporal_60_40",
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["target_id = ?", "split_name = ?"]
        params: list[Any] = [target_id, split_name]
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        if ti2026_only:
            clauses.append("team_name IN (SELECT team_name FROM analytics_ti2026_teams WHERE has_ewc_player_data = 1)")
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT chosen_family, chosen_model_id, target_id, split_name,
                   official_name, team_name, official_position, role_group,
                   predicted_score, q25, q50, q75, q90, maps_observed,
                   train_rows_used, metric_entity_spearman, metric_ndcg_5,
                   metric_top5_overlap, metric_mae, metric_regret_at_1
            FROM analytics_prediction_production_players
            {where}
            ORDER BY role_group, predicted_score DESC, official_name
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def production_prediction_role_slots(
    *,
    target_id: str = "role_slot_series_top1",
    split_name: str = "temporal_60_40",
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["target_id = ?", "split_name = ?"]
        params: list[Any] = [target_id, split_name]
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        if ti2026_only:
            clauses.append("team_name IN (SELECT team_name FROM analytics_ti2026_teams WHERE has_ewc_player_data = 1)")
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT chosen_family, chosen_model_id, target_id, split_name,
                   team_name, role_slot, player_names,
                   predicted_score, q25, q50, q75, q90, maps_observed,
                   train_rows_used, metric_entity_spearman, metric_ndcg_5,
                   metric_top5_overlap, metric_mae, metric_regret_at_1
            FROM analytics_prediction_production_role_slots
            {where}
            ORDER BY role_slot, predicted_score DESC, team_name
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def production_monte_carlo_players(
    *,
    target_id: str = "player_series_top1",
    split_name: str = "temporal_60_40",
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["target_id = ?", "split_name = ?"]
        params: list[Any] = [target_id, split_name]
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT target_id, split_name, team_name, official_name, official_position, role_group,
                   predicted_score, simulated_mean_score, simulated_std_score,
                   p_top1, p_top3, p_top5, expected_rank, p90_sim_score
            FROM analytics_prediction_monte_carlo_players
            {where}
            ORDER BY role_group, p_top1 DESC, p_top3 DESC, predicted_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def production_monte_carlo_role_slots(
    *,
    target_id: str = "role_slot_series_top1",
    split_name: str = "temporal_60_40",
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["target_id = ?", "split_name = ?"]
        params: list[Any] = [target_id, split_name]
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        if ti2026_only:
            clauses.append("ti2026_qualified = 1")
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT target_id, split_name, team_name, role_slot, player_names,
                   predicted_score, simulated_mean_score, simulated_std_score,
                   p_top1, p_top3, p_top5, expected_rank, p90_sim_score
            FROM analytics_prediction_monte_carlo_role_slots
            {where}
            ORDER BY role_slot, p_top1 DESC, p_top3 DESC, predicted_score DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_rescoring_players(
    *,
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["rescoring_scope = ?"]
        params: list[Any] = ["ti2026" if ti2026_only else "all"]
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT role_group, official_name, team_name, official_position,
                   rescore_score_1_100, predicted_anchor_score, p90_anchor_score,
                   p_top1_anchor, p_top3_anchor, p_top5_anchor,
                   expected_rank_anchor, stability_index, rank_strength_index,
                   surface_quality_index
            FROM analytics_banner_rescoring_players
            {where}
            ORDER BY role_group, rescore_score_1_100 DESC, rescore_raw DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_rescoring_role_slots(
    *,
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["rescoring_scope = ?"]
        params: list[Any] = ["ti2026" if ti2026_only else "all"]
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT role_slot, player_names, team_name,
                   rescore_score_1_100, predicted_anchor_score, p90_anchor_score,
                   p_top1_anchor, p_top3_anchor, p_top5_anchor,
                   expected_rank_anchor, stability_index, rank_strength_index,
                   surface_quality_index
            FROM analytics_banner_rescoring_role_slots
            {where}
            ORDER BY role_slot, rescore_score_1_100 DESC, rescore_raw DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_decision_players(
    *,
    risk_profile: str = "balanced",
    ti2026_only: bool = False,
    position: int | None = None,
    role_group: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["decision_scope = ?", "risk_profile = ?"]
        params: list[Any] = ["ti2026" if ti2026_only else "all", risk_profile]
        if position:
            clauses.append("official_position = ?")
            params.append(position)
        if role_group:
            clauses.append("role_group = ?")
            params.append(role_group)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT risk_profile, role_group, official_name, team_name, official_position,
                   decision_score_1_100, decision_raw, rationale
            FROM analytics_banner_decision_players
            {where}
            ORDER BY role_group, decision_score_1_100 DESC, decision_raw DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_decision_role_slots(
    *,
    risk_profile: str = "balanced",
    ti2026_only: bool = False,
    role_slot: str | None = None,
    team: str | None = None,
    limit: int = 15,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        clauses = ["decision_scope = ?", "risk_profile = ?"]
        params: list[Any] = ["ti2026" if ti2026_only else "all", risk_profile]
        if role_slot:
            clauses.append("role_slot = ?")
            params.append(role_slot)
        if team:
            clauses.append("team_name = ?")
            params.append(resolve_team(team, con) or team)
        where = "WHERE " + " AND ".join(clauses)
        return run_sql(
            f"""
            SELECT risk_profile, role_slot, player_names, team_name,
                   decision_score_1_100, decision_raw, rationale
            FROM analytics_banner_decision_role_slots
            {where}
            ORDER BY role_slot, decision_score_1_100 DESC, decision_raw DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def banner_decision_lineups(
    *,
    risk_profile: str = "balanced",
    ti2026_only: bool = False,
    limit: int = 10,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    own = con is None
    con = con or connect()
    try:
        scope = "ti2026" if ti2026_only else "all"
        return run_sql(
            f"""
            SELECT risk_profile, lineup_rank,
                   core_team_name, core_players, core_decision_score,
                   mid_team_name, mid_player, mid_decision_score,
                   support_team_name, support_players, support_decision_score,
                   lineup_score_1_100, rationale
            FROM analytics_banner_decision_lineups
            WHERE decision_scope = ?
              AND risk_profile = ?
            ORDER BY lineup_rank
            LIMIT {int(limit)}
            """,
            [scope, risk_profile],
            con,
        )
    finally:
        if own:
            con.close()


def try_gigachat_polish(question: str, draft: str, dataframes: dict[str, pd.DataFrame] | None = None) -> str:
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        return draft
    try:
        from langchain_gigachat.chat_models import GigaChat
    except Exception:
        return draft
    tables = []
    for name, df in (dataframes or {}).items():
        tables.append(f"[{name}]\n{df.head(20).to_string(index=False)}")
    context = "\n\n".join(tables)
    system = (
        "Ты факт-ориентированный аналитик EWC 2026 Dota 2. "
        "Не добавляй чисел вне переданных таблиц. Если данных не хватает, так и скажи. "
        "Ответ должен быть кратким, удобным и на русском."
    )
    prompt = f"Р’РѕРїСЂРѕСЃ: {question}\n\nР§РµСЂРЅРѕРІРёРє:\n{draft}\n\nРўР°Р±Р»РёС†С‹:\n{context}"
    for model in [os.getenv("GIGACHAT_MODEL"), "GigaChat-2", "GigaChat"]:
        if not model:
            continue
        try:
            llm = GigaChat(credentials=credentials, model=model, verify_ssl_certs=False, timeout=30)
            return llm.invoke([("system", system), ("human", prompt)]).content
        except Exception:
            continue
    return draft


class EWCFactAgent:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.con = connect(self.db_path)

    def close(self) -> None:
        self.con.close()

    def ask(self, question: str, max_rows: int | None = None, use_llm: bool = False) -> AgentResult:
        max_rows = max_rows or extract_limit(question)
        q = normalize_text(question)
        plan = decompose_question(question, self.con)
        dataframes: dict[str, pd.DataFrame] = {}
        source_notes = [f"SQLite: {self.db_path}"]
        sql_plan = build_sql_plan(question, self.con, limit=max_rows)
        plan.insert(0, f"SQL planner route: {sql_plan.route}; confidence={sql_plan.confidence}.")

        if sql_planner_requested(question):
            df = explain_sql_plan(question, self.con, limit=max_rows)
            dataframes["sql_plan"] = df
            answer = render_answer(
                "SQL planner",
                df,
                max_rows=max_rows,
                note=(
                    "This deterministic plan preview shows the SQLite route, filters, views, params and SQL template. "
                    "It does not invent missing external facts."
                ),
            )
            return self._finish(question, "sql_planner", answer, dataframes, plan, source_notes, use_llm=False)

        if any(token in q for token in ["С„РѕСЂРјСѓР»", "РєР°Рє СЃС‡РёС‚", "scoring", "РѕС‡РєРё СЃС‡РёС‚"]) and not banner_rescoring_requested(question):
            df = scoring_formula(con=self.con)
            dataframes["scoring_formula"] = df
            answer = render_answer(
                "Р¤РѕСЂРјСѓР»Р° fantasy-РѕС‡РєРѕРІ С‚РµРєСѓС‰РµРіРѕ РїСЂРѕС„РёР»СЏ",
                df,
                max_rows=max_rows,
                note=(
                    "Итог карты считается как сумма выбранных статов после применения их множителей "
                    "плюс возможный coach-title bonus. "
                    "`base_points_total` здесь означает x1-сумму только по статам активного баннера, "
                    "`profile_bonus_points` — uplift сверх x1 по тем же stat'ам, "
                    "а `title_bonus_points` — отдельный prefix/suffix слой, если у профиля настроены title-правила."
                ),
            )
            return self._finish(question, "scoring_formula", answer, dataframes, plan, source_notes, use_llm)

        if optimizer_v2_requested(question) and any(token in q for token in ["backtest", "quality", "evaluation", "бэктест", "качество"]):
            df = optimizer_v2_backtest(self.con)
            dataframes["optimizer_v2_backtest"] = df
            answer = render_answer("Optimizer v2 backtest", df, max_rows=max_rows)
            return self._finish(question, "optimizer_v2_backtest", answer, dataframes, plan, source_notes, use_llm=False)

        if optimizer_baselines_requested(question):
            df = optimizer_baselines_foundation(self.con)
            dataframes["optimizer_baselines_foundation"] = df
            answer = render_answer("Foundation optimizer vs baselines", df, max_rows=max_rows)
            return self._finish(question, "optimizer_baselines_foundation", answer, dataframes, plan, source_notes, use_llm=False)

        if optimizer_backtest_requested(question):
            df = optimizer_backtest_foundation(self.con)
            dataframes["optimizer_backtest_foundation"] = df
            answer = render_answer("Backtest foundation optimizer", df, max_rows=max_rows)
            return self._finish(question, "optimizer_backtest_foundation", answer, dataframes, plan, source_notes, use_llm=False)

        if prediction_backtest_requested(question):
            df = production_prediction_model_choices(self.con)
            dataframes["prediction_production_model_choices"] = df
            answer = render_answer(
                "Production prediction champions",
                df,
                max_rows=max_rows,
                note="This surface stores the current champion model per target/split. The selection is based on historical ranking quality, then reused as the default predictive layer for current player and role-slot scoring.",
            )
            return self._finish(question, "prediction_production_model_choices", answer, dataframes, plan, source_notes, use_llm=False)

        if banner_decision_requested(question):
            risk_profile = extract_risk_profile(question)
            ti_only = ti_filter_requested(question)
            role_slot = extract_role_slot(question)
            team = resolve_team(question, self.con)
            if any(token in q for token in ["lineup", "lineups", "лайнап", "состав"]):
                df = banner_decision_lineups(
                    risk_profile=risk_profile,
                    ti2026_only=ti_only,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["banner_decision_lineups"] = df
                answer = render_answer(
                    f"Banner decision lineups ({risk_profile})",
                    df,
                    max_rows=max_rows,
                    note="This is the practical decision layer built on top of banner rescoring. It returns ready-made three-team lineups for the selected risk profile.",
                )
                return self._finish(question, "banner_decision_lineups", answer, dataframes, plan, source_notes, use_llm=False)
            if role_slot:
                df = banner_decision_role_slots(
                    risk_profile=risk_profile,
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["banner_decision_role_slots"] = df
                answer = render_answer(
                    f"Banner decision role-slots ({risk_profile})",
                    df,
                    max_rows=max_rows,
                    note="This decision layer reweights upside and stability according to the selected risk profile.",
                )
                return self._finish(question, "banner_decision_role_slots", answer, dataframes, plan, source_notes, use_llm=False)
            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            df = banner_decision_players(
                risk_profile=risk_profile,
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["banner_decision_players"] = df
            answer = render_answer(
                f"Banner decision players ({risk_profile})",
                df,
                max_rows=max_rows,
                note="This decision layer reweights upside and stability according to the selected risk profile.",
            )
            return self._finish(question, "banner_decision_players", answer, dataframes, plan, source_notes, use_llm=False)

        if banner_rescoring_requested(question):
            ti_only = ti_filter_requested(question)
            role_slot = extract_role_slot(question)
            team = resolve_team(question, self.con)
            if role_slot:
                df = banner_rescoring_role_slots(
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["banner_rescoring_role_slots"] = df
                answer = render_answer(
                    "Banner rescoring role-slots",
                    df,
                    max_rows=max_rows,
                    note="This layer re-ranks role slots using weighted production prediction plus Monte Carlo upside and stability signals.",
                )
                return self._finish(question, "banner_rescoring_role_slots", answer, dataframes, plan, source_notes, use_llm=False)
            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            df = banner_rescoring_players(
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["banner_rescoring_players"] = df
            answer = render_answer(
                "Banner rescoring players",
                df,
                max_rows=max_rows,
                note="This layer re-ranks players using weighted production prediction plus Monte Carlo upside and stability signals.",
            )
            return self._finish(question, "banner_rescoring_players", answer, dataframes, plan, source_notes, use_llm=False)

        if monte_carlo_requested(question):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            if role_slot or pair_requested:
                target_id = extract_prediction_target(question, "role_slot")
                df = production_monte_carlo_role_slots(
                    target_id=target_id,
                    split_name="temporal_60_40",
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["prediction_monte_carlo_role_slots"] = df
                answer = render_answer(
                    "Monte Carlo role-slot stability",
                    df,
                    max_rows=max_rows,
                    note="This layer samples many tournament-like outcomes around the production prediction surface and estimates top-finish probabilities plus expected ranking stability.",
                )
                return self._finish(question, "prediction_monte_carlo_role_slots", answer, dataframes, plan, source_notes, use_llm=False)

            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            target_id = extract_prediction_target(question, "player")
            df = production_monte_carlo_players(
                target_id=target_id,
                split_name="temporal_60_40",
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["prediction_monte_carlo_players"] = df
            answer = render_answer(
                "Monte Carlo player stability",
                df,
                max_rows=max_rows,
                note="This layer samples many tournament-like outcomes around the production prediction surface and estimates top-finish probabilities plus expected ranking stability.",
            )
            return self._finish(question, "prediction_monte_carlo_players", answer, dataframes, plan, source_notes, use_llm=False)

        if prediction_requested(question):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            if role_slot or pair_requested:
                target_id = extract_prediction_target(question, "role_slot")
                df = production_prediction_role_slots(
                    target_id=target_id,
                    split_name="temporal_60_40",
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["prediction_production_role_slots"] = df
                answer = render_answer(
                    "Production prediction for role-slots",
                    df,
                    max_rows=max_rows,
                    note="This is the default model-based predictive surface. It uses the historically best-performing model family for the selected target and then rescored current entities on the full available dataset.",
                )
                return self._finish(question, "prediction_production_role_slots", answer, dataframes, plan, source_notes, use_llm=False)

            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            target_id = extract_prediction_target(question, "player")
            df = production_prediction_players(
                target_id=target_id,
                split_name="temporal_60_40",
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["prediction_production_players"] = df
            answer = render_answer(
                "Production prediction for players",
                df,
                max_rows=max_rows,
                note="This is the default model-based predictive surface. It uses the historically best-performing model family for the selected target and then rescored current entities on the full available dataset.",
            )
            return self._finish(question, "prediction_production_players", answer, dataframes, plan, source_notes, use_llm=False)

        if optimizer_v2_requested(question):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            if role_slot or pair_requested:
                df = optimizer_v2_role_slots(
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["optimizer_v2_role_slots"] = df
                answer = render_answer("Optimizer v2 role-slots", df, max_rows=max_rows)
                return self._finish(question, "optimizer_v2_role_slots", answer, dataframes, plan, source_notes, use_llm=False)
            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            df = optimizer_v2_players(
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["optimizer_v2_players"] = df
            answer = render_answer("Optimizer v2 players", df, max_rows=max_rows)
            return self._finish(question, "optimizer_v2_players", answer, dataframes, plan, source_notes, use_llm=False)

        if any(token in q for token in ["metric", "метрик", "что значит", "как считается", "definition", "объясни показатель", "объясни метрику"]) and not optimizer_requested(question):
            metric_name = None
            for candidate in [
                "fantasy_score",
                "base_points_total",
                "profile_bonus_points",
                "title_bonus_points",
                "map_mean_score",
                "map_p75_score",
                "map_p90_score",
                "series_mean_avg",
                "series_mean_p75",
                "series_top1_avg",
                "series_top1_p75",
                "series_top1_p90",
                "team_segment_strength",
                "positive_stat_count",
                "top_stat_share",
                "stat_balance_score",
                "volatility_ratio",
                "sample_weight",
                "reliability_raw_score",
                "reliability_score_1_100",
                "low_estimate",
                "expected_estimate",
                "high_estimate",
                "optimizer_raw_score",
                "optimizer_score_1_100",
                "best2_series_score",
                "repeatability_ratio",
                "spike_gap",
            ]:
                if candidate.lower() in question.lower():
                    metric_name = candidate
                    break
            df = metric_definitions(metric_name=metric_name, con=self.con)
            dataframes["metric_definitions"] = df
            title = "Metric definitions" if metric_name is None else f"Metric definition: {metric_name}"
            answer = render_answer(title, df, max_rows=max_rows)
            return self._finish(question, "metric_definitions", answer, dataframes, plan, source_notes, use_llm=False)

        if any(token in q for token in ["backtest", "Р±СЌРєС‚РµСЃС‚", "РєР°С‡РµСЃС‚РІРѕ РјРѕРґРµР»Рё", "РїСЂРѕРІРµСЂРєР° РјРѕРґРµР»Рё"]):
            df = reliability_backtest_foundation(self.con)
            dataframes["reliability_backtest_foundation"] = df
            answer = render_answer("Backtest foundation reliability", df, max_rows=max_rows)
            return self._finish(question, "reliability_backtest_foundation", answer, dataframes, plan, source_notes, use_llm)

        if (
            ti_filter_requested(question)
            and any(token in q for token in ["РєРѕРјР°РЅРґ", "teams", "СЃРїРёСЃРѕРє", "СѓС‡Р°СЃС‚РЅРёРє"])
            and not optimizer_requested(question)
            and not any(token in q for token in ["С‚РѕРї", "top", "Р»СѓС‡С€РёРµ", "С„РµРЅС‚РµР·Рё", "С„СЌРЅС‚РµР·Рё", "fantasy", "РѕС‡Рє"])
        ):
            df = ti_qualified_teams(self.con)
            dataframes["ti_qualified_teams"] = df
            answer = render_answer(
                "TI 2026 qualified teams РёР· source-cache",
                df,
                max_rows=max_rows,
                note="Р¤РёР»СЊС‚СЂ С…СЂР°РЅРёС‚СЃСЏ РІ SQLite: `ti_qualified_teams`; `has_ewc_player_data=1` Р·РЅР°С‡РёС‚, С‡С‚Рѕ РїРѕ РєРѕРјР°РЅРґРµ РµСЃС‚СЊ EWC-СЃС‚Р°С‚РёСЃС‚РёРєР°.",
            )
            return self._finish(question, "ti_qualified_teams", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["source cache", "external_source", "РєСЌС€", "РёСЃС‚РѕС‡РЅРёРєРё РІ Р±Р°Р·Рµ"]):
            df = source_cache_status(self.con)
            dataframes["source_cache_status"] = df
            answer = render_answer("External source cache", df, max_rows=max_rows)
            return self._finish(question, "source_cache_status", answer, dataframes, plan, source_notes, use_llm)

        if optimizer_requested(question):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            use_foundation = optimizer_foundation_requested(question)
            if role_slot or pair_requested:
                if use_foundation:
                    df = banner_optimizer_role_slots_foundation(
                        ti2026_only=ti_only,
                        role_slot=role_slot,
                        team=team,
                        limit=max_rows,
                        con=self.con,
                    )
                    dataframes["banner_optimizer_role_slots_foundation"] = df
                    title = "Foundation optimizer for fantasy role-slots"
                    if ti_only:
                        title += " among TI 2026 qualified teams"
                    answer = render_answer(
                        title,
                        df,
                        max_rows=max_rows,
                        note="Foundation optimizer combines expected/high estimates, reliability strength, p75 signals, stat balance, and volatility penalties.",
                    )
                    return self._finish(question, "banner_optimizer_role_slots_foundation", answer, dataframes, plan, source_notes, use_llm)

                df = banner_optimizer_role_slots_v2(
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["banner_optimizer_role_slots_v2"] = df
                title = "Optimizer v2 for fantasy role-slots"
                if ti_only:
                    title += " among TI 2026 qualified teams"
                answer = render_answer(
                    title,
                    df,
                    max_rows=max_rows,
                    note="Optimizer v2 is the default recommendation surface. It is a conservative ceiling-first ranker built mostly from upper-quantile series strength with lightweight penalties for one-stat dependence and volatility.",
                )
                return self._finish(question, "banner_optimizer_role_slots_v2", answer, dataframes, plan, source_notes, use_llm)

            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            if use_foundation:
                df = banner_optimizer_players_foundation(
                    ti2026_only=ti_only,
                    position=pos,
                    role_group=role,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["banner_optimizer_players_foundation"] = df
                title = "Foundation optimizer for fantasy players"
                if ti_only:
                    title += " among TI 2026 qualified teams"
                answer = render_answer(
                    title,
                    df,
                    max_rows=max_rows,
                    note="Foundation optimizer combines expected/high estimates, reliability strength, p75 signals, stat balance, and volatility penalties.",
                )
                return self._finish(question, "banner_optimizer_players_foundation", answer, dataframes, plan, source_notes, use_llm)

            df = banner_optimizer_players_v2(
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["banner_optimizer_players_v2"] = df
            title = "Optimizer v2 for fantasy players"
            if ti_only:
                title += " among TI 2026 qualified teams"
            answer = render_answer(
                title,
                df,
                max_rows=max_rows,
                note="Optimizer v2 is the default recommendation surface. It is a conservative ceiling-first ranker built mostly from upper-quantile series strength with lightweight penalties for one-stat dependence and volatility.",
            )
            return self._finish(question, "banner_optimizer_players_v2", answer, dataframes, plan, source_notes, use_llm)

        reliability_tokens = ["надеж", "надёж", "стабил", "риск", "reliable", "stable", "risk"]
        if any(token in q for token in reliability_tokens):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            explicit_support = True
            if role_slot or pair_requested:
                df = reliable_role_slots_foundation(
                    role_slot=role_slot,
                    team=team,
                    ti2026_only=ti_only,
                    limit=max_rows,
                    include_support=explicit_support,
                    con=self.con,
                )
                dataframes["reliable_role_slots_foundation"] = df
                note = SUPPORT_CAVEAT_RU if role_slot == "support_pair" else None
                answer = render_answer("Foundation reliability for fantasy role-slots", df, max_rows=max_rows, note=note)
                return self._finish(question, "reliable_role_slots_foundation", answer, dataframes, plan, source_notes, use_llm)

            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            df = reliable_players_foundation(
                position=pos,
                role_group=role,
                team=team,
                ti2026_only=ti_only,
                limit=max_rows,
                include_support=explicit_support,
                con=self.con,
            )
            dataframes["reliable_players_foundation"] = df
            note = SUPPORT_CAVEAT_RU if (role == "support" or pos in {4, 5}) else DEFAULT_RELIABILITY_SCOPE_RU
            answer = render_answer("Foundation reliability for fantasy players", df, max_rows=max_rows, note=note)
            return self._finish(question, "reliable_players_foundation", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["СЃРѕСЃС‚Р°РІ", "roster", "РёРіСЂРѕРєРё РєРѕРјР°РЅРґС‹"]):
            team = resolve_team(question, self.con)
            if team:
                df = roster(team, self.con)
                dataframes["roster"] = df
                answer = render_answer(f"РЎРѕСЃС‚Р°РІ {team}", df, max_rows=max_rows)
                return self._finish(question, "roster", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["avg core", "core + mid", "role-category", "СЂРѕР»СЊ", "СЃР»РѕС‚ РєРѕРјР°РЅРґС‹"]):
            team = resolve_team(question, self.con)
            df = role_map_summary(team=team, limit=max_rows, con=self.con)
            dataframes["role_map_summary"] = df
            answer = render_answer("Fantasy РїРѕ role-category РЅР° РєР°СЂС‚Р°С…", df, max_rows=max_rows)
            return self._finish(question, "role_map_summary", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["РєР°СЂС‚С‹ РёРіСЂРѕРєР°", "РїРѕ РєР°Р¶РґРѕР№ РєР°СЂС‚Рµ", "РїРѕ РјР°С‚С‡Р°Рј РёРіСЂРѕРєР°"]):
            player = extract_player(question, self.con)
            if player:
                df = player_maps(player, limit=max_rows, con=self.con)
                dataframes["player_maps"] = df
                answer = render_answer(f"РљР°СЂС‚С‹ РёРіСЂРѕРєР° {player}", df, max_rows=max_rows)
                return self._finish(question, "player_maps", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["С‚РѕРї", "top", "Р»СѓС‡С€РёРµ"]) and any(
            token in q for token in ["С„РµРЅС‚РµР·Рё", "С„СЌРЅС‚РµР·Рё", "fantasy", "РѕС‡Рє"]
        ):
            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            team = resolve_team(question, self.con)
            stage = extract_stage_bucket(question)
            ti_only = ti_filter_requested(question)
            df = top_fantasy_maps(
                position=pos,
                role_group=role,
                team=team,
                stage_bucket=stage,
                ti2026_only=ti_only,
                limit=max_rows,
                con=self.con,
            )
            dataframes["top_fantasy_maps"] = df
            answer = render_answer("Р›СѓС‡С€РёРµ fantasy-РєР°СЂС‚С‹", df, max_rows=max_rows)
            if ti_only:
                answer += (
                    "\n\nTI-С„РёР»СЊС‚СЂ РїСЂРёРјРµРЅРµРЅ РёР· SQLite-С‚Р°Р±Р»РёС†С‹ `ti_qualified_teams`; "
                    "РєРѕРјР°РЅРґС‹ Р±РµР· EWC-СЃС‚Р°С‚РёСЃС‚РёРєРё РЅРµ РїРѕРїР°РґР°СЋС‚ РІ СЂРµР№С‚РёРЅРі."
                )
                source_notes.append("TI 2026 filter applied from ti_qualified_teams.")
            elif needs_web_source(question):
                answer += (
                    "\n\nР’ Р·Р°РїСЂРѕСЃРµ РµСЃС‚СЊ РІРЅРµС€РЅРёР№ С„РёР»СЊС‚СЂ РІСЂРѕРґРµ TI-РєРІР°Р»РёС„РёРєР°С†РёРё. "
                    "Р•СЃР»Рё С‚Р°РєРѕРіРѕ СЃРїРёСЃРєР° РЅРµС‚ РІ SQLite, РЅСѓР¶РЅРѕ СЃРІРµСЂРёС‚СЊ РµРіРѕ С‡РµСЂРµР· Liquipedia/Dotabuff."
                )
                source_notes.append("Potential external filter requested.")
            return self._finish(question, "top_fantasy_maps", answer, dataframes, plan, source_notes, use_llm)

        if needs_web_source(question):
            df = source_urls(question, self.con)
            dataframes["source_urls"] = df
            answer = render_answer(
                "РџРѕРґС…РѕРґСЏС‰РёРµ РІРЅРµС€РЅРёРµ РёСЃС‚РѕС‡РЅРёРєРё",
                df,
                max_rows=max_rows,
                note="РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Р°РіРµРЅС‚ РЅРµ РІС‹РґСѓРјС‹РІР°РµС‚ РІРЅРµС€РЅРёРµ С„Р°РєС‚С‹: СЃРЅР°С‡Р°Р»Р° РґР°РµС‚ РёСЃС‚РѕС‡РЅРёРєРё, Р·Р°С‚РµРј РјРѕР¶РЅРѕ РІРєР»СЋС‡РёС‚СЊ fetch/СЂСѓС‡РЅСѓСЋ РїСЂРѕРІРµСЂРєСѓ.",
            )
            source_notes.append("External source needed for complete answer.")
            return self._finish(question, "source_urls", answer, dataframes, plan, source_notes, use_llm=False)

        df = db_status(self.con)
        dataframes["db_status"] = df
        answer = render_answer(
            "РЇ РЅРµ СѓРІРµСЂРµРЅ РІ РјР°СЂС€СЂСѓС‚Рµ, РїРѕСЌС‚РѕРјСѓ РїРѕРєР°Р·С‹РІР°СЋ СЃС‚Р°С‚СѓСЃ Р±Р°Р·С‹",
            df,
            max_rows=max_rows,
            note=(
                "РџРѕРїСЂРѕР±СѓР№ СѓС‚РѕС‡РЅРёС‚СЊ: `СЃРѕСЃС‚Р°РІ Team Liquid`, `С‚РѕРї fantasy pos1`, "
                "`РЅР°РґРµР¶РЅС‹Рµ core РїР°СЂС‹`, `backtest РјРѕРґРµР»Рё`, `С„РѕСЂРјСѓР»Р° РѕС‡РєРѕРІ`."
            ),
        )
        return self._finish(question, "fallback_db_status", answer, dataframes, plan, source_notes, use_llm=False)

    def _finish(
        self,
        question: str,
        route: str,
        answer: str,
        dataframes: dict[str, pd.DataFrame],
        plan: list[str],
        source_notes: list[str],
        use_llm: bool,
    ) -> AgentResult:
        if use_llm:
            answer = try_gigachat_polish(question, answer, dataframes)
        return AgentResult(
            question=question,
            route=route,
            answer_markdown=answer,
            dataframes=dataframes,
            plan=plan,
            source_notes=source_notes,
        )


def ask(question: str, max_rows: int | None = None, use_llm: bool = False, db_path: str | Path = DB_PATH) -> AgentResult:
    agent = EWCFactAgent(db_path)
    try:
        return agent.ask(question, max_rows=max_rows, use_llm=use_llm)
    finally:
        agent.close()


def chat(db_path: str | Path = DB_PATH, use_llm: bool = False) -> None:
    agent = EWCFactAgent(db_path)
    print("EWC 2026 fact-agent. Exit: q / quit / exit")
    try:
        while True:
            question = input("Р’РѕРїСЂРѕСЃ: ").strip()
            if question.lower() in {"q", "quit", "exit"}:
                break
            result = agent.ask(question, use_llm=use_llm)
            print("\n" + result.answer_markdown + "\n")
    finally:
        agent.close()


def explain_system_short() -> str:
    return textwrap.dedent(
        """
        Система работает source-first:
        1. Факты и числа берутся из SQLite.
        2. Fantasy score карты = сумма выбранных статов после применения множителей баннера.
        3. Reliability-v2 оценивает повторяемый потолок: p75/p90, recent form, volatility и sample trust.
        4. Optimizer и decision-слои используют foundation-метрики, а не старую best2-only логику.
        5. Support-слоты входят в общие рекомендации, но их utility-метрики полезно читать вместе с coverage.
        6. Внешние факты вроде актуальных составов и TI qualification при необходимости добираются из источников.
        """
    ).strip()



