from __future__ import annotations

import sqlite3
from typing import Any


PLAYOFF_TEMPLATE_ID = "ti2026_playoff_5slot_v1"

DEFAULT_QUALITY_RULES: list[dict[str, Any]] = [
    {"quality_tier": "tier_i", "display_name": "Tier I", "bonus_pct": 10.0, "roll_weight": 35.0, "notes": "Official quality boost from glossary."},
    {"quality_tier": "tier_ii", "display_name": "Tier II", "bonus_pct": 30.0, "roll_weight": 25.0, "notes": "Official quality boost from glossary."},
    {"quality_tier": "tier_iii", "display_name": "Tier III", "bonus_pct": 60.0, "roll_weight": 18.0, "notes": "Official quality boost from glossary."},
    {"quality_tier": "tier_iv", "display_name": "Tier IV", "bonus_pct": 100.0, "roll_weight": 14.0, "notes": "Official quality boost from glossary."},
    {"quality_tier": "tier_v", "display_name": "Tier V", "bonus_pct": 150.0, "roll_weight": 8.0, "notes": "Official quality boost from glossary."},
]

DEFAULT_TRAIT_RULES: list[dict[str, Any]] = [
    {
        "trait_name": "fractal",
        "display_name": "Fractal",
        "scope_kind": "self_conditional",
        "self_bonus_pct": 60.0,
        "adjacent_bonus_pct": 0.0,
        "adjacent_penalty_pct": 0.0,
        "condition_kind": "all_qualities_distinct",
        "condition_min_count": None,
        "roll_weight": 20.0,
        "notes": "Official glossary: +60% if all emblem qualities differ on the banner.",
    },
    {
        "trait_name": "benevolent",
        "display_name": "Benevolent",
        "scope_kind": "adjacent_positive",
        "self_bonus_pct": 0.0,
        "adjacent_bonus_pct": 20.0,
        "adjacent_penalty_pct": 0.0,
        "condition_kind": "always",
        "condition_min_count": None,
        "roll_weight": 20.0,
        "notes": "Official glossary: provides a 20% bonus to adjacent emblems.",
    },
    {
        "trait_name": "vampiric",
        "display_name": "Vampiric",
        "scope_kind": "self_plus_adjacent_penalty",
        "self_bonus_pct": 50.0,
        "adjacent_bonus_pct": 0.0,
        "adjacent_penalty_pct": 10.0,
        "condition_kind": "always",
        "condition_min_count": None,
        "roll_weight": 20.0,
        "notes": "Official glossary: +50% to this emblem, -10% to adjacent emblems.",
    },
    {
        "trait_name": "unique",
        "display_name": "Unique",
        "scope_kind": "self_conditional",
        "self_bonus_pct": 30.0,
        "adjacent_bonus_pct": 0.0,
        "adjacent_penalty_pct": 0.0,
        "condition_kind": "only_one_same_trait",
        "condition_min_count": 1,
        "roll_weight": 20.0,
        "notes": "Official glossary: +30% if it is the only Unique emblem on the banner.",
    },
    {
        "trait_name": "friendly",
        "display_name": "Friendly",
        "scope_kind": "self_conditional",
        "self_bonus_pct": 50.0,
        "adjacent_bonus_pct": 0.0,
        "adjacent_penalty_pct": 0.0,
        "condition_kind": "min_same_trait_count",
        "condition_min_count": 3,
        "roll_weight": 20.0,
        "notes": "Official glossary: +50% if at least 3 Friendly emblems exist on the banner.",
    },
]

DEFAULT_TEMPLATE_SLOTS: list[dict[str, Any]] = [
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "core", "slot_index": 1, "allowed_color_group": "red", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "core", "slot_index": 2, "allowed_color_group": "green", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "core", "slot_index": 3, "allowed_color_group": "red", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "core", "slot_index": 4, "allowed_color_group": "green", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "core", "slot_index": 5, "allowed_color_group": "red", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "mid", "slot_index": 1, "allowed_color_group": "red", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "mid", "slot_index": 2, "allowed_color_group": "blue", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "mid", "slot_index": 3, "allowed_color_group": "green", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "mid", "slot_index": 4, "allowed_color_group": "red", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "mid", "slot_index": 5, "allowed_color_group": "green", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "support", "slot_index": 1, "allowed_color_group": "blue", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "support", "slot_index": 2, "allowed_color_group": "green", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "support", "slot_index": 3, "allowed_color_group": "blue", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "support", "slot_index": 4, "allowed_color_group": "green", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
    {"template_id": PLAYOFF_TEMPLATE_ID, "event_id": "ti2026", "role_scope": "support", "slot_index": 5, "allowed_color_group": "blue", "slot_kind": "stat_slot", "required_flag": 1, "notes": "Playoff banner slot from observed UI."},
]


def ensure_complex_banner_schema(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_templates (
            template_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            template_name TEXT NOT NULL,
            slot_count_per_role INTEGER NOT NULL,
            source_label TEXT NOT NULL DEFAULT 'manual_seed',
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_template_slots (
            template_id TEXT NOT NULL,
            role_scope TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            allowed_color_group TEXT NOT NULL,
            slot_kind TEXT NOT NULL DEFAULT 'stat_slot',
            required_flag INTEGER NOT NULL DEFAULT 1 CHECK (required_flag IN (0, 1)),
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (template_id, role_scope, slot_index),
            FOREIGN KEY (template_id) REFERENCES fantasy_banner_templates(template_id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_instances (
            profile_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL DEFAULT 'ti2026',
            template_id TEXT,
            profile_name TEXT NOT NULL,
            source_label TEXT NOT NULL DEFAULT 'manual_profile',
            slot_count_per_role INTEGER,
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (profile_id) REFERENCES fantasy_scoring_profiles(profile_id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES fantasy_banner_templates(template_id) ON DELETE SET NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_instance_slots (
            profile_id TEXT NOT NULL,
            role_scope TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            stat_name TEXT NOT NULL,
            color_group TEXT,
            multiplier REAL NOT NULL DEFAULT 1.0,
            quality_tier TEXT,
            quality_bonus_pct REAL,
            trait_name TEXT,
            trait_bonus_pct REAL,
            adjacency_group TEXT,
            slot_kind TEXT NOT NULL DEFAULT 'stat_slot',
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            locked_flag INTEGER NOT NULL DEFAULT 0 CHECK (locked_flag IN (0, 1)),
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (profile_id, role_scope, slot_index),
            FOREIGN KEY (profile_id) REFERENCES fantasy_scoring_profiles(profile_id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_roll_rules (
            rule_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            token_type TEXT NOT NULL,
            action_scope TEXT NOT NULL,
            target_scope TEXT NOT NULL,
            distribution_json TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_quality_rules (
            quality_tier TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            bonus_pct REAL NOT NULL,
            roll_weight REAL NOT NULL DEFAULT 1.0,
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_trait_rules (
            trait_name TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            scope_kind TEXT NOT NULL,
            self_bonus_pct REAL NOT NULL DEFAULT 0.0,
            adjacent_bonus_pct REAL NOT NULL DEFAULT 0.0,
            adjacent_penalty_pct REAL NOT NULL DEFAULT 0.0,
            condition_kind TEXT NOT NULL DEFAULT 'always',
            condition_min_count INTEGER,
            roll_weight REAL NOT NULL DEFAULT 1.0,
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_roll_distributions (
            rule_id TEXT NOT NULL,
            item_kind TEXT NOT NULL,
            item_value TEXT NOT NULL,
            role_scope TEXT NOT NULL DEFAULT '',
            allowed_color_group TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 1.0,
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (rule_id, item_kind, item_value, role_scope, allowed_color_group),
            FOREIGN KEY (rule_id) REFERENCES fantasy_banner_roll_rules(rule_id) ON DELETE CASCADE
        )
        """
    )

    cur.execute("DROP VIEW IF EXISTS analytics_complex_banner_templates")
    cur.execute(
        """
        CREATE VIEW analytics_complex_banner_templates AS
        SELECT
            t.template_id,
            t.event_id,
            t.template_name,
            t.slot_count_per_role,
            s.role_scope,
            s.slot_index,
            s.allowed_color_group,
            s.slot_kind,
            s.required_flag,
            s.notes
        FROM fantasy_banner_templates t
        JOIN fantasy_banner_template_slots s
          ON s.template_id = t.template_id
        """
    )
    cur.execute("DROP VIEW IF EXISTS analytics_complex_banner_formula")
    cur.execute(
        """
        CREATE VIEW analytics_complex_banner_formula AS
        SELECT
            i.profile_id,
            i.event_id,
            i.template_id,
            i.profile_name,
            i.slot_count_per_role,
            s.role_scope,
            s.slot_index,
            s.slot_kind,
            s.stat_name,
            s.color_group,
            s.multiplier,
            s.quality_tier,
            s.quality_bonus_pct,
            s.trait_name,
            s.trait_bonus_pct,
            s.adjacency_group,
            s.enabled,
            s.locked_flag,
            s.notes
        FROM fantasy_banner_instances i
        JOIN fantasy_banner_instance_slots s
          ON s.profile_id = i.profile_id
        """
    )
    cur.execute("DROP VIEW IF EXISTS analytics_complex_banner_rulebook")
    cur.execute(
        """
        CREATE VIEW analytics_complex_banner_rulebook AS
        SELECT
            'quality' AS rule_family,
            quality_tier AS rule_key,
            display_name,
            bonus_pct AS primary_bonus_pct,
            roll_weight,
            notes
        FROM fantasy_banner_quality_rules
        UNION ALL
        SELECT
            'trait' AS rule_family,
            trait_name AS rule_key,
            display_name,
            self_bonus_pct AS primary_bonus_pct,
            roll_weight,
            notes
        FROM fantasy_banner_trait_rules
        """
    )


def seed_default_complex_banner_templates(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO fantasy_banner_templates(
            template_id, event_id, template_name, slot_count_per_role, source_label, notes, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            PLAYOFF_TEMPLATE_ID,
            "ti2026",
            "TI 2026 playoff five-slot banner",
            5,
            "manual_seed_from_observed_ui",
            "Observed playoff banner shape with five stat slots per role and fixed color layout.",
        ),
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_banner_template_slots(
            template_id, role_scope, slot_index, allowed_color_group, slot_kind, required_flag, notes, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        [
            (
                row["template_id"],
                row["role_scope"],
                row["slot_index"],
                row["allowed_color_group"],
                row["slot_kind"],
                row["required_flag"],
                row["notes"],
            )
            for row in DEFAULT_TEMPLATE_SLOTS
        ],
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_banner_quality_rules(
            quality_tier, display_name, bonus_pct, roll_weight, notes, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        [
            (
                row["quality_tier"],
                row["display_name"],
                row["bonus_pct"],
                row["roll_weight"],
                row["notes"],
            )
            for row in DEFAULT_QUALITY_RULES
        ],
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_banner_trait_rules(
            trait_name, display_name, scope_kind, self_bonus_pct, adjacent_bonus_pct,
            adjacent_penalty_pct, condition_kind, condition_min_count, roll_weight, notes, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        [
            (
                row["trait_name"],
                row["display_name"],
                row["scope_kind"],
                row["self_bonus_pct"],
                row["adjacent_bonus_pct"],
                row["adjacent_penalty_pct"],
                row["condition_kind"],
                row["condition_min_count"],
                row["roll_weight"],
                row["notes"],
            )
            for row in DEFAULT_TRAIT_RULES
        ],
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_banner_roll_rules(
            rule_id, event_id, token_type, action_scope, target_scope, distribution_json, notes, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        [
            (
                "ti2026_generic_reroll_stat_v1",
                "ti2026",
                "reroll_stat",
                "single_slot",
                "stat_only",
                '{"sampler":"stat_by_allowed_color"}',
                "Generic baseline stat reroll rule seeded before real token frequencies are known.",
            ),
            (
                "ti2026_generic_reroll_quality_v1",
                "ti2026",
                "reroll_quality",
                "single_slot",
                "quality_only",
                '{"sampler":"quality_catalog_weighted"}',
                "Generic baseline quality reroll rule seeded from official tier glossary.",
            ),
            (
                "ti2026_generic_reroll_trait_v1",
                "ti2026",
                "reroll_trait",
                "single_slot",
                "trait_only",
                '{"sampler":"trait_catalog_weighted"}',
                "Generic baseline trait reroll rule seeded from official trait glossary.",
            ),
            (
                "ti2026_generic_reroll_emblem_v1",
                "ti2026",
                "reroll_emblem",
                "single_slot",
                "stat_quality_trait",
                '{"sampler":"full_slot_resample"}',
                "Generic baseline emblem reroll rule seeded before real token frequencies are known.",
            ),
        ],
    )


def infer_slot_count_per_role(banner_spec: dict[str, list[dict[str, Any] | tuple[str, float]]]) -> int | None:
    counts = [len(entries) for role_scope, entries in banner_spec.items() if role_scope in {"core", "mid", "support"}]
    if not counts:
        return None
    if len(set(counts)) == 1:
        return counts[0]
    return max(counts)
