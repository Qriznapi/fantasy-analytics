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


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_db_path(project_root: Path = PROJECT_ROOT) -> Path:
    candidates = [
        project_root / "data" / "ewc_2026_fantasy_compact.sqlite",
        project_root / "data" / "db" / "ewc_2026_fantasy_compact.sqlite",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DB_PATH = resolve_db_path()

SUPPORT_CAVEAT_RU = (
    "Важно: по саппортам в этой базе статистика неполная и заметно менее полезная. "
    "По умолчанию надежность fantasy-пика лучше оценивать по позициям 1-3 "
    "и слотам core_pair/mid_single; саппортов стоит смотреть только как low-confidence справку."
)

DEFAULT_RELIABILITY_SCOPE_RU = (
    "Саппорты исключены из дефолтного рейтинга надежности, потому что support-статистика "
    "в текущей базе неполная. Для них можно сделать отдельный explicit-запрос."
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
        return "_Нет строк под этот запрос._"
    shown = df.head(max_rows)
    return "```text\n" + shown.to_string(index=False) + "\n```"


def render_answer(title: str, df: pd.DataFrame, max_rows: int = 12, note: str | None = None) -> str:
    parts = [f"### {title}", "", df_block(df, max_rows)]
    if len(df) > max_rows:
        parts.append(f"\nПоказано {max_rows} из {len(df)} строк.")
    if note:
        parts.extend(["", note])
    return "\n".join(parts)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("ё", "е")).strip()


def extract_limit(question: str, default: int = 15) -> int:
    q = normalize_text(question)
    m = re.search(r"\bтоп\s*(\d+)\b|\btop\s*(\d+)\b", q)
    if not m:
        return default
    value = int(next(group for group in m.groups() if group))
    return max(1, min(value, 100))


def extract_position(question: str) -> int | None:
    q = normalize_text(question)
    patterns = [
        r"\bpos\s*([1-5])\b",
        r"\bпозици[ия]\s*([1-5])\b",
        r"\b([1-5])\s*позици[ия]\b",
        r"\b([1-5])\s*поз\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            return int(m.group(1))
    return None


def extract_role_group(question: str) -> str | None:
    q = normalize_text(question)
    if any(token in q for token in ["сап", "саппорт", "support", "pos4", "pos5"]):
        return "support"
    if any(token in q for token in ["мид", "mid", "мидер", "pos2"]):
        return "mid"
    if any(token in q for token in ["кор", "core", "керри", "carry", "offlane", "оффлейн", "pos1", "pos3"]):
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
    return any(token in q for token in ["ti 2026", "the international", "отобрав", "квалифиц"])


def optimizer_requested(question: str) -> bool:
    q = normalize_text(question)
    return any(token in q for token in ["оптим", "optimizer", "баннер", "banner", "кого ставить", "кого брать"])


def extract_role_slot(question: str) -> str | None:
    q = normalize_text(question)
    if any(token in q for token in ["support_pair", "support pair", "пара сап", "сап пары", "саппорт пары"]):
        return "support_pair"
    if any(token in q for token in ["core_pair", "core pair", "пара кор", "кор пары", "core пары", "коры"]):
        return "core_pair"
    if any(token in q for token in ["mid_single", "mid single", "мид слот", "мидер"]):
        return "mid_single"
    return None


def extract_stage_bucket(question: str) -> str | None:
    q = normalize_text(question)
    if any(token in q for token in ["плейофф", "плей-офф", "playoff", "playoffs"]):
        return "playoffs"
    if any(token in q for token in ["группа", "группов", "group", "survival"]):
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
    if any(token in q for token in ["надеж", "надeж", "стабил", "пик", "выбор", "reliable"]):
        steps.append("Определить, что это запрос на reliability fantasy-пика.")
    if any(token in q for token in ["фентези", "фэнтези", "fantasy"]):
        steps.append("Использовать fantasy-профиль и сохраненные fantasy_score из SQLite.")
    if team:
        steps.append(f"Отфильтровать команду: {team}.")
    if player:
        steps.append(f"Отфильтровать игрока: {player}.")
    if pos:
        steps.append(f"Отфильтровать официальную позицию: pos{pos}.")
    elif role:
        steps.append(f"Отфильтровать роль: {role}.")
    if stage:
        steps.append(f"Отфильтровать стадию: {stage}.")
    if "ti" in q or "отобрав" in q or "квалифиц" in q:
        steps.append("Проверить внешний источник для состава/списка TI-квалифицированных команд.")
    steps.append(f"Вернуть не больше {limit} строк и явно назвать источник данных.")
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

        if any(token in q for token in ["С„РѕСЂРјСѓР»", "РєР°Рє СЃС‡РёС‚", "scoring", "РѕС‡РєРё СЃС‡РёС‚"]):
            sql = """
                SELECT profile_id, role_scope, banner_slot, stat_name,
                       multiplier, quality_tier, trait, enabled, notes
                FROM analytics_scoring_formula
                ORDER BY role_scope, banner_slot
            """
            return SQLPlan(
                question=question,
                route="scoring_formula",
                intent="explain fantasy scoring profile",
                tables_or_views=["analytics_scoring_formula", "fantasy_scoring_profile_banners", "fantasy_scoring_profile_stats"],
                filters=filters,
                metrics=["multiplier", "enabled"],
                sql=compact_sql(sql),
                confidence="high",
            )

        if any(token in q for token in ["backtest", "Р±СЌРєС‚РµСЃС‚", "РєР°С‡РµСЃС‚РІРѕ РјРѕРґРµР»Рё", "РїСЂРѕРІРµСЂРєР° РјРѕРґРµР»Рё"]):
            sql = """
                SELECT entity_type, segment_name, n_test, mae, rmse,
                       spearman_corr, top5_overlap_rate, top10_overlap_rate
                FROM analytics_reliability_backtest
                ORDER BY entity_type, segment_name
            """
            return SQLPlan(
                question=question,
                route="reliability_backtest_v2",
                intent="evaluate reliability-v2 backtest",
                tables_or_views=["analytics_reliability_backtest"],
                filters=filters,
                metrics=["mae", "rmse", "spearman_corr", "top5_overlap_rate", "top10_overlap_rate"],
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
                view = "analytics_optimizer_role_slots"
                clauses: list[str] = []
                params: list[Any] = []
                clauses.append("optimizer_scope = ?")
                params.append("ti2026" if ti_only else "all")
                if role_slot:
                    clauses.append("role_slot = ?")
                    params.append(role_slot)
                if team:
                    clauses.append("team_name = ?")
                    params.append(team)
                where = "WHERE " + " AND ".join(clauses) if clauses else ""
                sql = f"""
                    SELECT optimizer_score_1_100, team_name, role_slot, player_names,
                           predicted_score_raw, best2_series_score, second_best2_series_score,
                           repeatability_ratio, spike_gap, train_series_seen,
                           ti2026_qualified, qualification_path, ti_region,
                           data_quality_label, recommendation_note
                    FROM {view}
                    {where}
                    ORDER BY role_slot, optimizer_score_1_100 DESC, predicted_score_raw DESC
                    LIMIT {int(max_rows)}
                """
                return SQLPlan(
                    question=question,
                    route="banner_optimizer_role_slots",
                    intent="rank fantasy role-slot picks by optimizer score",
                    tables_or_views=[view, "fantasy_banner_optimizer_recommendations"],
                    filters=filters,
                    metrics=["optimizer_score_1_100", "predicted_score_raw", "repeatability_ratio", "spike_gap"],
                    sql=compact_sql(sql),
                    params=params,
                    confidence="high",
                )

            view = "analytics_optimizer_players"
            clauses = []
            params = []
            clauses.append("optimizer_scope = ?")
            params.append("ti2026" if ti_only else "all")
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
                       official_position, role_group, predicted_score_raw,
                       best2_series_score, second_best2_series_score,
                       repeatability_ratio, spike_gap, train_series_seen,
                       ti2026_qualified, qualification_path, ti_region,
                       data_quality_label, recommendation_note
                FROM {view}
                {where}
                ORDER BY role_group, optimizer_score_1_100 DESC, predicted_score_raw DESC
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="banner_optimizer_players",
                intent="rank fantasy player picks by optimizer score",
                tables_or_views=[view, "fantasy_banner_optimizer_recommendations"],
                filters=filters,
                metrics=["optimizer_score_1_100", "predicted_score_raw", "repeatability_ratio", "spike_gap"],
                sql=compact_sql(sql),
                params=params,
                confidence="high",
            )

        reliability_tokens = ["РЅР°РґРµР¶", "РЅР°РґeР¶", "СЃС‚Р°Р±РёР»", "РїСЂРёРІР»РµРєР°С‚РµР»СЊ", "РІС‹Р±РѕСЂ", "РїРёРє", "reliable", "СЂРёСЃРє"]
        if any(token in q for token in reliability_tokens):
            pair_requested = any(token in q for token in ["РїР°СЂР°", "pair", "СЃРІСЏР·РєР°", "СЃР»РѕС‚"])
            if role_slot or pair_requested:
                view = "analytics_reliable_role_slots"
                clauses = []
                params = []
                if role_slot != "support_pair":
                    clauses.append("recommended_default = 1")
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
                           predicted_score_raw, low_estimate, expected_estimate, high_estimate,
                           uncertainty_score, confidence_label,
                           best2_series_score AS train_best2_series_score,
                           repeatability_ratio, spike_gap, train_series_seen, data_quality_label
                    FROM {view}
                    {where}
                    ORDER BY role_slot, reliability_score_1_100 DESC, predicted_score_raw DESC
                    LIMIT {int(max_rows)}
                """
                return SQLPlan(
                    question=question,
                    route="reliable_role_slots_v2",
                    intent="rank reliable fantasy role-slot picks with intervals",
                    tables_or_views=[view, "fantasy_reliability_v2_role_slot_predictions"],
                    filters=filters,
                    metrics=["reliability_score_1_100", "low_estimate", "expected_estimate", "high_estimate"],
                    sql=compact_sql(sql),
                    params=params,
                    confidence="high",
                )

            view = "analytics_reliable_players"
            clauses = []
            params = []
            if not support_requested(question):
                clauses.append("recommended_default = 1")
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
                LIMIT {int(max_rows)}
            """
            return SQLPlan(
                question=question,
                route="reliable_players_v2",
                intent="rank reliable fantasy player picks with intervals",
                tables_or_views=[view, "fantasy_reliability_v2_player_predictions"],
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
                       won, duration_sec, base_points_total, profile_bonus_points
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
                metrics=["fantasy_score", "base_points_total", "profile_bonus_points"],
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
            "analytics_reliable_players",
            "analytics_reliable_role_slots",
            "analytics_optimizer_players",
            "analytics_optimizer_role_slots",
            "analytics_reliability_backtest",
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
    own = con is None
    con = con or connect()
    try:
        explicit_support = role_group == "support" or position in {4, 5}
        if include_support is None:
            include_support = explicit_support
        view = "analytics_reliable_players"
        clauses = []
        params: list[Any] = []
        if not include_support:
            clauses.append("recommended_default = 1")
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
                   official_position, role_group, predicted_score_raw,
                   low_estimate, expected_estimate, high_estimate,
                   uncertainty_score, confidence_label,
                   best2_series_score AS train_best2_series_score,
                   second_best2_series_score AS train_second_best2_series_score,
                   repeatability_ratio, spike_gap, shrinkage_weight,
                   uncertainty_penalty, train_series_seen, data_quality_label
            FROM {view}
            {where}
            ORDER BY reliability_score_1_100 DESC, predicted_score_raw DESC
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
    own = con is None
    con = con or connect()
    try:
        explicit_support = role_slot == "support_pair"
        if include_support is None:
            include_support = explicit_support
        view = "analytics_reliable_role_slots"
        clauses = []
        params: list[Any] = []
        if not include_support:
            clauses.append("recommended_default = 1")
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
                   predicted_score_raw,
                   best2_series_score AS train_best2_series_score,
                   low_estimate, expected_estimate, high_estimate,
                   uncertainty_score, confidence_label,
                   second_best2_series_score AS train_second_best2_series_score,
                   repeatability_ratio, spike_gap,
                   shrinkage_weight, uncertainty_penalty, train_series_seen,
                   data_quality_label
            FROM {view}
            {where}
            ORDER BY role_slot, reliability_score_1_100 DESC, predicted_score_raw DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


def reliability_backtest_v2(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    return run_sql(
        """
        SELECT entity_type, segment_name, n_test, mae, rmse,
               spearman_corr, top5_overlap_rate, top10_overlap_rate
        FROM analytics_reliability_backtest
        ORDER BY entity_type, segment_name
        """,
        con=con,
    )


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


def banner_optimizer_players(
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
        view = "analytics_optimizer_players"
        clauses = []
        params: list[Any] = []
        clauses.append("optimizer_scope = ?")
        params.append("ti2026" if ti2026_only else "all")
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
                   official_position, role_group, predicted_score_raw,
                   best2_series_score, second_best2_series_score,
                   repeatability_ratio, spike_gap, train_series_seen,
                   ti2026_qualified, qualification_path, ti_region,
                   data_quality_label, recommendation_note
            FROM {view}
            {where}
            ORDER BY role_group, optimizer_score_1_100 DESC, predicted_score_raw DESC
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
    own = con is None
    con = con or connect()
    try:
        view = "analytics_optimizer_role_slots"
        clauses = []
        params: list[Any] = []
        clauses.append("optimizer_scope = ?")
        params.append("ti2026" if ti2026_only else "all")
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
                   predicted_score_raw, best2_series_score,
                   second_best2_series_score, repeatability_ratio, spike_gap,
                   train_series_seen, ti2026_qualified, qualification_path,
                   ti_region, data_quality_label, recommendation_note
            FROM {view}
            {where}
            ORDER BY role_slot, optimizer_score_1_100 DESC, predicted_score_raw DESC
            LIMIT {int(limit)}
            """,
            params,
            con,
        )
    finally:
        if own:
            con.close()


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
                   won, duration_sec, base_points_total, profile_bonus_points
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
                SELECT profile_id, role_scope, banner_slot, stat_name,
                       multiplier, quality_tier, trait, enabled, notes
                FROM analytics_scoring_formula
                ORDER BY role_scope, banner_slot
                """,
                con=con,
            )
        return run_sql(
            """
            SELECT b.profile_id, b.role_scope, b.banner_slot, b.stat_name,
                   b.multiplier, b.quality_tier, b.trait, s.enabled, s.notes
            FROM fantasy_scoring_profile_banners b
            LEFT JOIN fantasy_scoring_profile_stats s
              ON s.profile_id = b.profile_id
             AND s.role_scope = b.role_scope
             AND s.stat_name = b.stat_name
            WHERE b.profile_id = ?
            ORDER BY b.role_scope, b.banner_slot
            """,
            (profile_id,),
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
        "интернет",
        "сайт",
        "источник",
        "liquipedia",
        "ликвипед",
        "dotabuff",
        "дотабафф",
        "opendota",
        "ti 2026",
        "the international",
        "отобрав",
        "квалифиц",
    ]
    return any(token in q for token in tokens)


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
    prompt = f"Вопрос: {question}\n\nЧерновик:\n{draft}\n\nТаблицы:\n{context}"
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
        source_notes = [f"SQLite: {DB_PATH}"]
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

        if any(token in q for token in ["формул", "как счит", "scoring", "очки счит"]):
            df = scoring_formula(con=self.con)
            dataframes["scoring_formula"] = df
            answer = render_answer(
                "Формула fantasy-очков текущего профиля",
                df,
                max_rows=max_rows,
                note=(
                    "Итог карты считается как `base_points_total + profile_bonus_points`. "
                    "Base points берутся из battlepass-статистик, а bonus добавляет выбранные banner stats "
                    "по официальной роли игрока."
                ),
            )
            return self._finish(question, "scoring_formula", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["backtest", "бэктест", "качество модели", "проверка модели"]):
            df = reliability_backtest_v2(self.con)
            dataframes["reliability_backtest_v2"] = df
            answer = render_answer("Backtest reliability-v2", df, max_rows=max_rows)
            return self._finish(question, "reliability_backtest_v2", answer, dataframes, plan, source_notes, use_llm)

        if (
            ti_filter_requested(question)
            and any(token in q for token in ["команд", "teams", "список", "участник"])
            and not optimizer_requested(question)
            and not any(token in q for token in ["топ", "top", "лучшие", "фентези", "фэнтези", "fantasy", "очк"])
        ):
            df = ti_qualified_teams(self.con)
            dataframes["ti_qualified_teams"] = df
            answer = render_answer(
                "TI 2026 qualified teams из source-cache",
                df,
                max_rows=max_rows,
                note="Фильтр хранится в SQLite: `ti_qualified_teams`; `has_ewc_player_data=1` значит, что по команде есть EWC-статистика.",
            )
            return self._finish(question, "ti_qualified_teams", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["source cache", "external_source", "кэш", "источники в базе"]):
            df = source_cache_status(self.con)
            dataframes["source_cache_status"] = df
            answer = render_answer("External source cache", df, max_rows=max_rows)
            return self._finish(question, "source_cache_status", answer, dataframes, plan, source_notes, use_llm)

        if optimizer_requested(question):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["пара", "pair", "связка", "слот"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            if role_slot or pair_requested:
                df = banner_optimizer_role_slots(
                    ti2026_only=ti_only,
                    role_slot=role_slot,
                    team=team,
                    limit=max_rows,
                    con=self.con,
                )
                dataframes["banner_optimizer_role_slots"] = df
                title = "Оптимизатор fantasy-слотов"
                if ti_only:
                    title += " среди TI 2026 qualified"
                answer = render_answer(title, df, max_rows=max_rows)
                return self._finish(question, "banner_optimizer_role_slots", answer, dataframes, plan, source_notes, use_llm)

            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            df = banner_optimizer_players(
                ti2026_only=ti_only,
                position=pos,
                role_group=role,
                team=team,
                limit=max_rows,
                con=self.con,
            )
            dataframes["banner_optimizer_players"] = df
            title = "Оптимизатор fantasy-игроков"
            if ti_only:
                title += " среди TI 2026 qualified"
            answer = render_answer(
                title,
                df,
                max_rows=max_rows,
                note="Optimizer использует текущий fantasy-профиль, повторяемый потолок, штраф за spike/volatility и по умолчанию не включает саппортов.",
            )
            return self._finish(question, "banner_optimizer_players", answer, dataframes, plan, source_notes, use_llm)

        reliability_tokens = ["надеж", "надeж", "стабил", "привлекатель", "выбор", "пик", "reliable", "риск"]
        if any(token in q for token in reliability_tokens):
            role_slot = extract_role_slot(question)
            pair_requested = any(token in q for token in ["пара", "pair", "связка", "слот"])
            team = resolve_team(question, self.con)
            ti_only = ti_filter_requested(question)
            explicit_support = support_requested(question) or role_slot == "support_pair"
            if role_slot or pair_requested:
                df = reliable_role_slots_v2(
                    role_slot=role_slot,
                    team=team,
                    ti2026_only=ti_only,
                    limit=max_rows,
                    include_support=explicit_support,
                    con=self.con,
                )
                dataframes["reliable_role_slots_v2"] = df
                note = SUPPORT_CAVEAT_RU if explicit_support else None
                answer = render_answer("Надежность fantasy-слотов v2", df, max_rows=max_rows, note=note)
                return self._finish(question, "reliable_role_slots_v2", answer, dataframes, plan, source_notes, use_llm)

            pos = extract_position(question)
            role = extract_role_group(question) or position_to_role_group(pos)
            df = reliable_players_v2(
                position=pos,
                role_group=role,
                team=team,
                ti2026_only=ti_only,
                limit=max_rows,
                include_support=explicit_support,
                con=self.con,
            )
            dataframes["reliable_players_v2"] = df
            note = SUPPORT_CAVEAT_RU if explicit_support else DEFAULT_RELIABILITY_SCOPE_RU
            answer = render_answer("Надежность fantasy-игроков v2", df, max_rows=max_rows, note=note)
            return self._finish(question, "reliable_players_v2", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["состав", "roster", "игроки команды"]):
            team = resolve_team(question, self.con)
            if team:
                df = roster(team, self.con)
                dataframes["roster"] = df
                answer = render_answer(f"Состав {team}", df, max_rows=max_rows)
                return self._finish(question, "roster", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["avg core", "core + mid", "role-category", "роль", "слот команды"]):
            team = resolve_team(question, self.con)
            df = role_map_summary(team=team, limit=max_rows, con=self.con)
            dataframes["role_map_summary"] = df
            answer = render_answer("Fantasy по role-category на картах", df, max_rows=max_rows)
            return self._finish(question, "role_map_summary", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["карты игрока", "по каждой карте", "по матчам игрока"]):
            player = extract_player(question, self.con)
            if player:
                df = player_maps(player, limit=max_rows, con=self.con)
                dataframes["player_maps"] = df
                answer = render_answer(f"Карты игрока {player}", df, max_rows=max_rows)
                return self._finish(question, "player_maps", answer, dataframes, plan, source_notes, use_llm)

        if any(token in q for token in ["топ", "top", "лучшие"]) and any(
            token in q for token in ["фентези", "фэнтези", "fantasy", "очк"]
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
            answer = render_answer("Лучшие fantasy-карты", df, max_rows=max_rows)
            if ti_only:
                answer += (
                    "\n\nTI-фильтр применен из SQLite-таблицы `ti_qualified_teams`; "
                    "команды без EWC-статистики не попадают в рейтинг."
                )
                source_notes.append("TI 2026 filter applied from ti_qualified_teams.")
            elif needs_web_source(question):
                answer += (
                    "\n\nВ запросе есть внешний фильтр вроде TI-квалификации. "
                    "Если такого списка нет в SQLite, нужно сверить его через Liquipedia/Dotabuff."
                )
                source_notes.append("Potential external filter requested.")
            return self._finish(question, "top_fantasy_maps", answer, dataframes, plan, source_notes, use_llm)

        if needs_web_source(question):
            df = source_urls(question, self.con)
            dataframes["source_urls"] = df
            answer = render_answer(
                "Подходящие внешние источники",
                df,
                max_rows=max_rows,
                note="По умолчанию агент не выдумывает внешние факты: сначала дает источники, затем можно включить fetch/ручную проверку.",
            )
            source_notes.append("External source needed for complete answer.")
            return self._finish(question, "source_urls", answer, dataframes, plan, source_notes, use_llm=False)

        df = db_status(self.con)
        dataframes["db_status"] = df
        answer = render_answer(
            "Я не уверен в маршруте, поэтому показываю статус базы",
            df,
            max_rows=max_rows,
            note=(
                "Попробуй уточнить: `состав Team Liquid`, `топ fantasy pos1`, "
                "`надежные core пары`, `backtest модели`, `формула очков`."
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
            question = input("Вопрос: ").strip()
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
        2. Fantasy score карты = base_points_total + profile_bonus_points.
        3. Reliability-v2 оценивает повторяемый потолок: best2-series, top2/top3, p75, recent form.
        4. V2 добавляет Bayesian shrinkage к медиане роли и штрафует одиночные выбросы/волатильность.
        5. Саппорты исключены из дефолтных рекомендаций из-за неполной support-статистики.
        6. Внешние факты вроде TI qualification требуют Liquipedia/Dotabuff/OpenDota.
        """
    ).strip()
