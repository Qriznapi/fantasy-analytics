from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_roll_simulator import RollAction, load_banner_slots, simulate_rollouts
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ti2026")
BENCHMARK_DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ewc2026")
DEFAULT_PRESET_PATH = PROJECT_ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json"
DEFAULT_RISK_PROFILES = ("conservative", "balanced", "aggressive")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if math.isnan(value):
        return default
    return value


def rank_scale_1_100(values: pd.Series) -> pd.Series:
    if len(values) == 0:
        return values
    if len(values) == 1:
        return pd.Series([100.0], index=values.index)
    ranks = values.rank(method="average", ascending=True)
    return (1.0 + 99.0 * (ranks - 1.0) / (len(values) - 1.0)).round(2)


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_policy_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            benchmark_event_id TEXT NOT NULL,
            preset_id TEXT NOT NULL,
            preset_path TEXT NOT NULL,
            objective_mode TEXT NOT NULL,
            simulations_per_action INTEGER NOT NULL,
            sample_store_limit INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_action_rollups (
            run_id TEXT NOT NULL,
            risk_profile TEXT NOT NULL,
            action_rank INTEGER NOT NULL,
            action_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            benchmark_event_id TEXT NOT NULL,
            token_type TEXT NOT NULL,
            role_scope TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            slot_label TEXT NOT NULL,
            current_stat_name TEXT NOT NULL,
            current_quality_tier TEXT,
            current_trait_name TEXT,
            current_multiplier REAL NOT NULL,
            expected_intrinsic_value_raw REAL NOT NULL,
            median_intrinsic_value_raw REAL NOT NULL,
            p75_intrinsic_value_raw REAL NOT NULL,
            p90_intrinsic_value_raw REAL NOT NULL,
            min_intrinsic_value_raw REAL NOT NULL,
            max_intrinsic_value_raw REAL NOT NULL,
            expected_delta_raw REAL NOT NULL,
            median_delta_raw REAL NOT NULL,
            p75_delta_raw REAL NOT NULL,
            p90_delta_raw REAL NOT NULL,
            min_delta_raw REAL NOT NULL,
            max_delta_raw REAL NOT NULL,
            positive_rate REAL NOT NULL,
            downside_rate REAL NOT NULL,
            baseline_intrinsic_value_raw REAL NOT NULL,
            simulations INTEGER NOT NULL,
            policy_raw REAL NOT NULL,
            policy_score_1_100 REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, risk_profile, action_id)
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_transition_samples (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            simulation_index INTEGER NOT NULL,
            next_intrinsic_value_raw REAL NOT NULL,
            delta_raw REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, action_id, simulation_index)
        );
        """
    )
    rebuild_views(con)


def rebuild_views(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP VIEW IF EXISTS analytics_rng_policy_runs;
        CREATE VIEW analytics_rng_policy_runs AS
        SELECT *
        FROM fantasy_rng_policy_runs;

        DROP VIEW IF EXISTS analytics_rng_action_rollups;
        CREATE VIEW analytics_rng_action_rollups AS
        SELECT a.*
        FROM fantasy_rng_action_rollups a
        JOIN (
            SELECT profile_id, MAX(created_at_utc) AS created_at_utc
            FROM fantasy_rng_policy_runs
            GROUP BY profile_id
        ) latest
          ON latest.profile_id = a.profile_id
        JOIN fantasy_rng_policy_runs r
          ON r.run_id = a.run_id
         AND r.created_at_utc = latest.created_at_utc;

        DROP VIEW IF EXISTS analytics_rng_best_actions;
        CREATE VIEW analytics_rng_best_actions AS
        SELECT *
        FROM analytics_rng_action_rollups
        WHERE action_rank = 1;
        """
    )


def load_token_preset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("preset_id", path.stem)
    payload.setdefault("token_specs", [])
    return payload


def _normalize_slot_indices(value: Any) -> list[int] | None:
    if value in (None, "all", "*"):
        return None
    if isinstance(value, list):
        return [int(item) for item in value]
    return [int(value)]


def _slot_label(slot: dict[str, Any]) -> str:
    return (
        f"{slot['role_scope']}#{int(slot['slot_index'])} | "
        f"{slot['stat_name']} | {slot.get('quality_tier') or '-'} | {slot.get('trait_name') or '-'}"
    )


def enumerate_candidate_actions(
    con: sqlite3.Connection,
    profile_id: str,
    preset: dict[str, Any],
) -> list[dict[str, Any]]:
    slots = load_banner_slots(con, profile_id)
    rows: list[dict[str, Any]] = []
    # High-fidelity presets retain observed token IDs.  An offer contains a token,
    # then the player chooses a legal role target; split token mass across targets.
    exact_tokens = [dict(item) for item in preset.get("token_offer_distribution", []) if float(item.get("adjusted_count", 0)) > 0]
    if exact_tokens:
        for token in exact_tokens:
            color = str(token.get("color_group", "")).lower()
            scope = str(token.get("scope", ""))
            family = str(token.get("generic_token_type", ""))
            candidates: list[tuple[str, int, str]] = []
            for role in ("core", "mid", "support"):
                matching = [slot for slot in slots if str(slot["role_scope"]) == role and (not color or str(slot.get("color_group", "")).lower() == color)]
                if not matching:
                    continue
                matching.sort(key=lambda slot: int(slot["slot_index"]))
                if scope == "all": candidates.append((role, -1, "role_color_all"))
                elif scope == "first": candidates.append((role, int(matching[0]["slot_index"]), "slot"))
                elif scope == "last": candidates.append((role, int(matching[-1]["slot_index"]), "slot"))
                elif scope == "random_one": candidates.append((role, -1, "role_color_random"))
                elif scope == "shift_plus1": candidates.append((role, -1, "role_quality_shift_plus1"))
                elif scope == "shift_plus2_minus1": candidates.append((role, -1, "role_quality_shift_plus2_minus1"))
            if not candidates:
                continue
            per_target_weight = safe_float(token.get("adjusted_count", 0.0), 0.0) / len(candidates)
            for role, slot_index, action_scope in candidates:
                token_id = str(token["token_id"])
                rows.append({"action_id": f"{token_id}::{role}::{slot_index}", "token_id": token_id, "token_type": family, "display_name": token_id, "role_scope": role, "slot_index": slot_index, "action_scope": action_scope, "target_color_group": color, "slot_label": f"{role} | {scope} {color}".strip(), "current_stat_name": "", "current_quality_tier": "", "current_trait_name": "", "current_multiplier": 0.0, "offer_weight": per_target_weight, "notes": "Exact empirical token-id action."})
        return sorted(rows, key=lambda item: (item["token_id"], item["role_scope"], item["slot_index"]))
    for token_spec in preset.get("token_specs", []):
        if not bool(token_spec.get("enabled", True)):
            continue
        role_scopes = set(token_spec.get("role_scopes", ["core", "mid", "support"]))
        action_scope = str(token_spec.get("action_scope", "slot"))
        target_color_group = str(token_spec.get("target_color_group", ""))
        if action_scope == "role_color_all":
            for role_scope in sorted(role_scopes):
                matching = [slot for slot in slots if str(slot["role_scope"]) == role_scope and str(slot.get("color_group", "")).lower() == target_color_group.lower()]
                if not matching:
                    continue
                action_id = f"{token_spec['token_type']}::{role_scope}::all_{target_color_group}"
                rows.append({"action_id": action_id, "token_type": str(token_spec["token_type"]), "display_name": str(token_spec.get("display_name", token_spec["token_type"])), "role_scope": role_scope, "slot_index": -1, "action_scope": action_scope, "target_color_group": target_color_group, "slot_label": f"{role_scope} | all {target_color_group}", "current_stat_name": "", "current_quality_tier": "", "current_trait_name": "", "current_multiplier": 0.0, "offer_weight": safe_float(token_spec.get("offer_weight", 1.0), 1.0), "notes": str(token_spec.get("notes", ""))})
            continue
        slot_indices = _normalize_slot_indices(token_spec.get("slot_indices", "all"))
        for slot in slots:
            if str(slot["role_scope"]) not in role_scopes:
                continue
            if slot_indices is not None and int(slot["slot_index"]) not in slot_indices:
                continue
            action_id = f"{token_spec['token_type']}::{slot['role_scope']}::{int(slot['slot_index'])}"
            rows.append(
                {
                    "action_id": action_id,
                    "token_id": str(token_spec.get("token_id", token_spec["token_type"])),
                    "token_type": str(token_spec["token_type"]),
                    "display_name": str(token_spec.get("display_name", token_spec["token_type"])),
                    "role_scope": str(slot["role_scope"]),
                    "slot_index": int(slot["slot_index"]),
                    "action_scope": action_scope,
                    "target_color_group": target_color_group,
                    "slot_label": _slot_label(slot),
                    "current_stat_name": str(slot["stat_name"]),
                    "current_quality_tier": str(slot.get("quality_tier") or ""),
                    "current_trait_name": str(slot.get("trait_name") or ""),
                    "current_multiplier": safe_float(slot.get("multiplier", 1.0), 1.0),
                    "offer_weight": safe_float(token_spec.get("offer_weight", 1.0), 1.0),
                    "notes": str(token_spec.get("notes", "")),
                }
            )
    rows.sort(key=lambda item: (item["role_scope"], item["slot_index"], item["token_type"]))
    return rows


def _policy_raw_for_row(row: pd.Series, risk_profile: str) -> float:
    expected_delta = safe_float(row["expected_delta_raw"])
    p75_delta = safe_float(row["p75_delta_raw"])
    p90_delta = safe_float(row["p90_delta_raw"])
    min_delta = safe_float(row["min_delta_raw"])
    max_delta = safe_float(row["max_delta_raw"])
    positive_rate = safe_float(row["positive_rate"])
    downside_rate = safe_float(row["downside_rate"])

    if risk_profile == "conservative":
        raw = (
            0.55 * p75_delta
            + 0.25 * expected_delta
            + 0.10 * p90_delta
            + 0.10 * (positive_rate * max(1.0, abs(expected_delta)))
            - 0.35 * downside_rate * abs(min(0.0, min_delta))
        )
    elif risk_profile == "aggressive":
        raw = (
            0.25 * expected_delta
            + 0.20 * p75_delta
            + 0.35 * p90_delta
            + 0.20 * max_delta
            - 0.15 * downside_rate * abs(min(0.0, min_delta))
        )
    else:
        raw = (
            0.40 * expected_delta
            + 0.30 * p75_delta
            + 0.20 * p90_delta
            + 0.10 * (positive_rate * max(1.0, abs(expected_delta)))
            - 0.20 * downside_rate * abs(min(0.0, min_delta))
        )
    return round(raw, 4)


def _store_transition_samples(
    cur: sqlite3.Cursor,
    run_id: str,
    action_id: str,
    baseline_value: float,
    outcomes: list[float],
    *,
    sample_store_limit: int,
) -> None:
    if sample_store_limit <= 0 or not outcomes:
        return
    rows = []
    for simulation_index, next_value in enumerate(outcomes[:sample_store_limit]):
        rows.append(
            (
                run_id,
                action_id,
                int(simulation_index),
                float(next_value),
                float(next_value) - float(baseline_value),
                utc_now(),
            )
        )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_rng_transition_samples(
            run_id, action_id, simulation_index, next_intrinsic_value_raw, delta_raw, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def build_rng_policy_foundation(
    *,
    profile_id: str,
    db_path: Path = TARGET_DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    preset_path: Path = DEFAULT_PRESET_PATH,
    objective_mode: str = "balanced",
    simulations_per_action: int = 250,
    sample_store_limit: int = 0,
    risk_profiles: tuple[str, ...] = DEFAULT_RISK_PROFILES,
) -> dict[str, Any]:
    preset = load_token_preset(preset_path)
    bootstrap_con = sqlite3.connect(str(db_path))
    try:
        create_schema(bootstrap_con)
        action_specs = enumerate_candidate_actions(bootstrap_con, profile_id, preset)
        event_row = bootstrap_con.execute(
            "SELECT COALESCE(event_id, 'ti2026') FROM fantasy_banner_instances WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        event_id = str(event_row[0]) if event_row else "ti2026"
        run_id = f"rng_foundation::{profile_id}::{utc_now()}"
    finally:
        bootstrap_con.close()

    rollup_rows: list[dict[str, Any]] = []
    transition_payloads: list[tuple[str, float, list[float]]] = []
    for action_spec in action_specs:
        result = simulate_rollouts(
            profile_id=profile_id,
            db_path=db_path,
            benchmark_db_path=benchmark_db_path,
            benchmark_event_id=benchmark_event_id,
            actions=[
                RollAction(
                    token_type=action_spec["token_type"],
                    role_scope=action_spec["role_scope"],
                    slot_index=action_spec["slot_index"],
                )
            ],
            simulations=simulations_per_action,
            objective_mode=objective_mode,
            example_count=0,
            return_outcomes=sample_store_limit > 0,
        )
        for risk_profile in risk_profiles:
            row = {
                **action_spec,
                "run_id": run_id,
                "profile_id": profile_id,
                "event_id": event_id,
                "benchmark_event_id": benchmark_event_id,
                "risk_profile": risk_profile,
                "expected_intrinsic_value_raw": safe_float(result["expected_intrinsic_value_raw"]),
                "median_intrinsic_value_raw": safe_float(result["median_intrinsic_value_raw"]),
                "p75_intrinsic_value_raw": safe_float(result["p75_intrinsic_value_raw"]),
                "p90_intrinsic_value_raw": safe_float(result["p90_intrinsic_value_raw"]),
                "min_intrinsic_value_raw": safe_float(result["min_intrinsic_value_raw"]),
                "max_intrinsic_value_raw": safe_float(result["max_intrinsic_value_raw"]),
                "expected_delta_raw": safe_float(result["expected_delta_raw"]),
                "median_delta_raw": safe_float(result["median_delta_raw"]),
                "p75_delta_raw": safe_float(result["p75_delta_raw"]),
                "p90_delta_raw": safe_float(result["p90_delta_raw"]),
                "min_delta_raw": safe_float(result["min_delta_raw"]),
                "max_delta_raw": safe_float(result["max_delta_raw"]),
                "positive_rate": safe_float(result["positive_rate"]),
                "downside_rate": safe_float(result["downside_rate"]),
                "baseline_intrinsic_value_raw": safe_float(result["baseline_intrinsic_value_raw"]),
                "simulations": int(result["simulations"]),
            }
            row["policy_raw"] = _policy_raw_for_row(pd.Series(row), risk_profile)
            rollup_rows.append(row)
        transition_payloads.append(
            (
                action_spec["action_id"],
                safe_float(result["baseline_intrinsic_value_raw"]),
                [safe_float(value) for value in result.get("outcomes", [])],
            )
        )

    rollup_df = pd.DataFrame(rollup_rows)
    if not rollup_df.empty:
        ranked_parts: list[pd.DataFrame] = []
        for risk_profile, group in rollup_df.groupby("risk_profile", sort=False):
            part = group.copy()
            part["policy_score_1_100"] = rank_scale_1_100(part["policy_raw"]).round(2)
            part = part.sort_values(
                ["policy_score_1_100", "policy_raw", "expected_delta_raw", "p75_delta_raw"],
                ascending=[False, False, False, False],
            ).reset_index(drop=True)
            part["action_rank"] = range(1, len(part) + 1)
            ranked_parts.append(part)
        rollup_df = pd.concat(ranked_parts, ignore_index=True)
    else:
        rollup_df["policy_score_1_100"] = []
        rollup_df["action_rank"] = []

    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        cur = con.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO fantasy_rng_policy_runs(
                run_id, profile_id, event_id, benchmark_event_id, preset_id, preset_path, objective_mode,
                simulations_per_action, sample_store_limit, created_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                profile_id,
                event_id,
                benchmark_event_id,
                str(preset.get("preset_id", preset_path.stem)),
                str(preset_path),
                objective_mode,
                int(simulations_per_action),
                int(sample_store_limit),
                utc_now(),
                "RNG foundation run built with placeholder token preset until real token frequencies are provided.",
            ),
        )
        cur.execute("DELETE FROM fantasy_rng_transition_samples WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_rng_action_rollups WHERE run_id = ?", (run_id,))
        for action_id, baseline_value, outcomes in transition_payloads:
            _store_transition_samples(
                cur,
                run_id,
                action_id,
                baseline_value,
                outcomes,
                sample_store_limit=sample_store_limit,
            )

        if not rollup_df.empty:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_rng_action_rollups(
                    run_id, risk_profile, action_rank, action_id, profile_id, event_id, benchmark_event_id,
                    token_type, role_scope, slot_index, slot_label, current_stat_name, current_quality_tier,
                    current_trait_name, current_multiplier, expected_intrinsic_value_raw, median_intrinsic_value_raw,
                    p75_intrinsic_value_raw, p90_intrinsic_value_raw, min_intrinsic_value_raw, max_intrinsic_value_raw,
                    expected_delta_raw, median_delta_raw, p75_delta_raw, p90_delta_raw, min_delta_raw, max_delta_raw,
                    positive_rate, downside_rate, baseline_intrinsic_value_raw, simulations, policy_raw, policy_score_1_100,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row.risk_profile,
                        int(row.action_rank),
                        row.action_id,
                        profile_id,
                        event_id,
                        benchmark_event_id,
                        row.token_type,
                        row.role_scope,
                        int(row.slot_index),
                        row.slot_label,
                        row.current_stat_name,
                        row.current_quality_tier,
                        row.current_trait_name,
                        float(row.current_multiplier),
                        float(row.expected_intrinsic_value_raw),
                        float(row.median_intrinsic_value_raw),
                        float(row.p75_intrinsic_value_raw),
                        float(row.p90_intrinsic_value_raw),
                        float(row.min_intrinsic_value_raw),
                        float(row.max_intrinsic_value_raw),
                        float(row.expected_delta_raw),
                        float(row.median_delta_raw),
                        float(row.p75_delta_raw),
                        float(row.p90_delta_raw),
                        float(row.min_delta_raw),
                        float(row.max_delta_raw),
                        float(row.positive_rate),
                        float(row.downside_rate),
                        float(row.baseline_intrinsic_value_raw),
                        int(row.simulations),
                        float(row.policy_raw),
                        float(row.policy_score_1_100),
                        utc_now(),
                    )
                    for row in rollup_df.itertuples(index=False)
                ],
            )

        con.commit()
        rebuild_views(con)
        summary_df = (
            rollup_df.groupby("risk_profile", as_index=False)
            .agg(
                action_count=("action_id", "count"),
                best_policy_score_1_100=("policy_score_1_100", "max"),
                best_expected_delta_raw=("expected_delta_raw", "max"),
                avg_expected_delta_raw=("expected_delta_raw", "mean"),
            )
            if not rollup_df.empty
            else pd.DataFrame()
        )
        return {
            "run_id": run_id,
            "profile_id": profile_id,
            "event_id": event_id,
            "benchmark_event_id": benchmark_event_id,
            "preset_id": str(preset.get("preset_id", preset_path.stem)),
            "rollup_df": rollup_df,
            "summary_df": summary_df,
        }
    finally:
        con.close()
