from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fantasy_rng_episode import (
    BENCHMARK_DB_PATH,
    DEFAULT_PRESET_PATH,
    TARGET_DB_PATH,
    EpisodeContext,
    _sample_offers,
    build_episode_context,
    evaluate_slots,
)
from fantasy_rng_foundation import enumerate_candidate_actions
from fantasy_rng_initial_state import load_initial_state_preset, sample_initial_slots_from_preset
from fantasy_roll_simulator import RollAction, apply_roll_action
from fantasy_roll_objective import load_role_stat_benchmarks, load_rule_maps, synchronize_effective_slot_fields
from fantasy_roll_simulator import (
    build_distribution_index,
    load_banner_slots,
    load_profile_meta,
    load_roll_distributions,
    load_template_color_map,
)
from fantasy_rng_preferences import preference_breakdown


@dataclass
class RNGOffer:
    action_id: str
    token_id: str
    token_type: str
    role_scope: str
    slot_index: int
    current_stat_name: str
    current_quality_tier: str
    current_trait_name: str
    current_multiplier: float
    offer_weight: float
    is_refresh_action: bool = False
    action_scope: str = "slot"
    target_color_group: str = ""


@dataclass
class RNGStepResult:
    offers: list[RNGOffer]
    chosen_offer: RNGOffer
    value_before: float
    value_after: float
    delta_value: float
    step_index: int
    done: bool


@dataclass
class RNGTokenOffer:
    token_id: str
    token_type: str
    action_scope: str
    target_color_group: str
    offer_weight: float


class RNGEnvironment:
    def __init__(
        self,
        *,
        profile_id: str,
        db_path: Path = TARGET_DB_PATH,
        benchmark_db_path: Path = BENCHMARK_DB_PATH,
        benchmark_event_id: str = "ewc2026",
        preset_path: Path = DEFAULT_PRESET_PATH,
        initial_state_preset_path: Path | None = None,
        objective_mode: str = "balanced",
        max_steps: int = 30,
        offers_per_step: int = 3,
        seed: int = 7,
    ) -> None:
        self.profile_id = str(profile_id)
        self.db_path = Path(db_path)
        self.benchmark_db_path = Path(benchmark_db_path)
        self.benchmark_event_id = str(benchmark_event_id)
        self.preset_path = Path(preset_path)
        self.initial_state_preset_path = Path(initial_state_preset_path) if initial_state_preset_path else None
        self.objective_mode = str(objective_mode)
        self.max_steps = int(max_steps)
        self.offers_per_step = int(offers_per_step)
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.ctx: EpisodeContext = self._build_context()
        self._action_specs = self._load_action_specs()
        self._base_slots = [dict(slot) for slot in self.ctx.base_slots]
        self._initial_state_preset = (
            load_initial_state_preset(self.initial_state_preset_path)
            if self.initial_state_preset_path
            else None
        )
        self._slots = [dict(slot) for slot in self._base_slots]
        self._step_index = 0
        self._last_offers: list[RNGOffer] = []
        self._last_token_offers: list[RNGTokenOffer] = []

    @classmethod
    def _from_existing(
        cls,
        source: "RNGEnvironment",
        *,
        seed: int | None = None,
    ) -> "RNGEnvironment":
        cloned = cls.__new__(cls)
        cloned.profile_id = source.profile_id
        cloned.db_path = source.db_path
        cloned.benchmark_db_path = source.benchmark_db_path
        cloned.benchmark_event_id = source.benchmark_event_id
        cloned.preset_path = source.preset_path
        cloned.initial_state_preset_path = source.initial_state_preset_path
        cloned._initial_state_preset = source._initial_state_preset
        cloned.objective_mode = source.objective_mode
        cloned.max_steps = source.max_steps
        cloned.offers_per_step = source.offers_per_step
        cloned.seed = source.seed if seed is None else int(seed)
        cloned.rng = random.Random(cloned.seed)
        cloned.ctx = source.ctx
        cloned._action_specs = source._action_specs
        cloned._base_slots = [dict(slot) for slot in source._base_slots]
        cloned._slots = [dict(slot) for slot in source._slots]
        cloned._step_index = int(source._step_index)
        cloned._last_offers = [RNGOffer(**offer.__dict__) for offer in source._last_offers]
        cloned._last_token_offers = [RNGTokenOffer(**offer.__dict__) for offer in source._last_token_offers]
        return cloned

    def _load_action_specs(self) -> list[dict[str, Any]]:
        con = sqlite3.connect(str(self.db_path))
        try:
            return enumerate_candidate_actions(con, self.profile_id, self.ctx.preset)
        finally:
            con.close()

    def _build_context(self) -> EpisodeContext:
        try:
            return build_episode_context(
                profile_id=self.profile_id,
                db_path=self.db_path,
                benchmark_db_path=self.benchmark_db_path,
                benchmark_event_id=self.benchmark_event_id,
                preset_path=self.preset_path,
            )
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
        target_con = sqlite3.connect(str(self.db_path))
        benchmark_con = sqlite3.connect(str(self.benchmark_db_path))
        try:
            meta = load_profile_meta(target_con, self.profile_id)
            base_slots = load_banner_slots(target_con, self.profile_id)
            template_color_map = load_template_color_map(target_con, meta["template_id"])
            benchmark_df = load_role_stat_benchmarks(benchmark_con)
            quality_map, trait_map = load_rule_maps(target_con)
            distribution_indices: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = {}
            for token_type in ["reroll_stat", "reroll_quality", "reroll_trait", "reroll_emblem"]:
                rule_id = f"ti2026_generic_{token_type}_v1"
                distribution_indices[rule_id] = build_distribution_index(load_roll_distributions(target_con, rule_id))
            from fantasy_rng_foundation import load_token_preset

            preset = load_token_preset(self.preset_path)
            return EpisodeContext(
                profile_id=self.profile_id,
                event_id=meta["event_id"],
                benchmark_event_id=self.benchmark_event_id,
                base_slots=[dict(slot) for slot in base_slots],
                template_color_map=template_color_map,
                benchmark_df=benchmark_df,
                quality_map=quality_map,
                trait_map=trait_map,
                distribution_indices=distribution_indices,
                preset=preset,
            )
        finally:
            benchmark_con.close()
            target_con.close()

    def clone(self, *, seed: int | None = None) -> "RNGEnvironment":
        return RNGEnvironment._from_existing(self, seed=seed)

    def reset(self, *, seed: int | None = None) -> list[dict[str, Any]]:
        if seed is not None:
            self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self._slots = [dict(slot) for slot in self._base_slots]
        if self._initial_state_preset is not None:
            # Sampling is reset with the episode seed, so matched evaluations share starts.
            self._slots = sample_initial_slots_from_preset(
                self._slots,
                self._initial_state_preset,
                rng=self.rng,
            )
        self._slots = synchronize_effective_slot_fields(
            self._slots, self.ctx.quality_map, self.ctx.trait_map
        )
        self._step_index = 0
        self._last_offers = []
        self._last_token_offers = []
        return self.state_slots()

    def state_slots(self) -> list[dict[str, Any]]:
        return [dict(slot) for slot in self._slots]

    def set_state_slots(self, slots: list[dict[str, Any]]) -> None:
        """Load a manually transcribed client banner into the active episode."""
        expected = {(str(slot["role_scope"]), int(slot["slot_index"])) for slot in self._base_slots}
        received = {(str(slot.get("role_scope")), int(slot.get("slot_index", -1))) for slot in slots}
        if received != expected:
            raise ValueError("Manual banner must contain exactly the 15 expected role/slot rows")
        merged: list[dict[str, Any]] = []
        base_by_key = {(str(slot["role_scope"]), int(slot["slot_index"])): slot for slot in self._base_slots}
        for supplied in slots:
            key = (str(supplied["role_scope"]), int(supplied["slot_index"]))
            row = dict(base_by_key[key])
            row.update({name: supplied[name] for name in ("stat_name", "quality_tier", "trait_name") if name in supplied})
            merged.append(row)
        for role in ("core", "mid", "support"):
            names = [str(slot["stat_name"]) for slot in merged if str(slot["role_scope"]) == role]
            if len(names) != len(set(names)):
                raise ValueError(f"Manual banner has duplicate stats in role {role}")
        self._slots = synchronize_effective_slot_fields(merged, self.ctx.quality_map, self.ctx.trait_map)

    def current_value(self) -> float:
        return float(evaluate_slots(self._slots, self.ctx, self.objective_mode))

    def current_preference_bonus(self) -> float:
        """Auxiliary strategic signal; it never replaces the official value."""
        return float(preference_breakdown(self._slots, self.ctx, self.objective_mode)["preference_bonus"])

    def current_guided_value(self, preference_weight: float = 0.0) -> float:
        return self.current_value() + float(preference_weight) * self.current_preference_bonus()

    def steps_remaining(self) -> int:
        return max(0, self.max_steps - self._step_index)

    def set_steps_remaining(self, remaining: int) -> None:
        """Align a manually loaded client banner with its remaining roll tokens."""
        remaining = int(remaining)
        if not 0 <= remaining <= self.max_steps:
            raise ValueError(f"remaining roll tokens must be between 0 and {self.max_steps}")
        self._step_index = self.max_steps - remaining

    def done(self) -> bool:
        return self._step_index >= self.max_steps

    def sample_offers(self) -> list[RNGOffer]:
        offers = _sample_offers(self.rng, self._action_specs, self.offers_per_step)
        self._last_offers = [
            RNGOffer(
                action_id=str(item["action_id"]),
                token_id=str(item.get("token_id", item["token_type"])),
                token_type=str(item["token_type"]),
                role_scope=str(item["role_scope"]),
                slot_index=int(item["slot_index"]),
                current_stat_name=str(item.get("current_stat_name", "")),
                current_quality_tier=str(item.get("current_quality_tier", "")),
                current_trait_name=str(item.get("current_trait_name", "")),
                current_multiplier=float(item.get("current_multiplier", 0.0)),
                offer_weight=float(item.get("offer_weight", 1.0)),
                is_refresh_action=bool(item.get("is_refresh_action", False)),
                action_scope=str(item.get("action_scope", "slot")),
                target_color_group=str(item.get("target_color_group", "")),
            )
            for item in offers
        ]
        self._last_offers.append(
            RNGOffer(
                action_id="refresh_offers",
                token_type="refresh_offers",
                token_id="refresh_offers",
                role_scope="global",
                slot_index=-1,
                current_stat_name="",
                current_quality_tier="",
                current_trait_name="",
                current_multiplier=0.0,
                offer_weight=1.0,
                is_refresh_action=True,
            )
        )
        return [RNGOffer(**offer.__dict__) for offer in self._last_offers]

    def sample_token_offers(self) -> list[RNGTokenOffer]:
        """Sample three token IDs first; role targeting is a later player decision."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for action in self._action_specs:
            grouped.setdefault(str(action.get("token_id", action["token_type"])), []).append(action)
        pool = []
        for token_id, actions in grouped.items():
            first = actions[0]
            pool.append({"token_id": token_id, "token_type": str(first["token_type"]), "action_scope": str(first.get("action_scope", "slot")), "target_color_group": str(first.get("target_color_group", "")), "offer_weight": sum(float(item.get("offer_weight", 0.0)) for item in actions)})
        selected: list[RNGTokenOffer] = []
        for _ in range(min(self.offers_per_step, len(pool))):
            total = sum(max(float(item["offer_weight"]), 0.0) for item in pool)
            pick = self.rng.random() * total if total > 0 else 0.0
            running = 0.0; index = len(pool) - 1
            for idx, item in enumerate(pool):
                running += max(float(item["offer_weight"]), 0.0)
                if running >= pick: index = idx; break
            item = pool.pop(index); selected.append(RNGTokenOffer(**item))
        self._last_token_offers = selected
        return [RNGTokenOffer(**item.__dict__) for item in selected]

    def legal_actions_for_token(self, token_id: str) -> list[RNGOffer]:
        actions = [item for item in self._action_specs if str(item.get("token_id", item["token_type"])) == str(token_id)]
        return [RNGOffer(action_id=str(item["action_id"]), token_id=str(item.get("token_id", item["token_type"])), token_type=str(item["token_type"]), role_scope=str(item["role_scope"]), slot_index=int(item["slot_index"]), current_stat_name=str(item.get("current_stat_name", "")), current_quality_tier=str(item.get("current_quality_tier", "")), current_trait_name=str(item.get("current_trait_name", "")), current_multiplier=float(item.get("current_multiplier", 0.0)), offer_weight=float(item.get("offer_weight", 1.0)), is_refresh_action=False, action_scope=str(item.get("action_scope", "slot")), target_color_group=str(item.get("target_color_group", ""))) for item in actions]

    def sample_decision_offers(self) -> list[RNGOffer]:
        """Return legal token+role choices after first sampling three token IDs."""
        tokens = self.sample_token_offers()
        actions = [action for token in tokens for action in self.legal_actions_for_token(token.token_id)]
        actions.append(RNGOffer(action_id="refresh_offers", token_id="refresh_offers", token_type="refresh_offers", role_scope="global", slot_index=-1, current_stat_name="", current_quality_tier="", current_trait_name="", current_multiplier=0.0, offer_weight=1.0, is_refresh_action=True))
        self._last_offers = [RNGOffer(**action.__dict__) for action in actions]
        return [RNGOffer(**action.__dict__) for action in actions]

    def step_action(self, action: RNGOffer) -> RNGStepResult:
        self._last_offers = [RNGOffer(**action.__dict__)]
        return self.step(0)

    def step(self, chosen_offer_index: int) -> RNGStepResult:
        if self.done():
            raise RuntimeError("Episode already finished")
        if not self._last_offers:
            self.sample_offers()
        if chosen_offer_index < 0 or chosen_offer_index >= len(self._last_offers):
            raise IndexError(f"chosen_offer_index={chosen_offer_index} is out of range")
        value_before = self.current_value()
        chosen_offer = self._last_offers[chosen_offer_index]
        if not chosen_offer.is_refresh_action:
            action = RollAction(
                token_type=chosen_offer.token_type,
                role_scope=chosen_offer.role_scope,
                slot_index=chosen_offer.slot_index,
                action_scope=chosen_offer.action_scope,
                target_color_group=chosen_offer.target_color_group,
            )
            distribution_index = self.ctx.distribution_indices[f"ti2026_generic_{chosen_offer.token_type}_v1"]
            self._slots = apply_roll_action(
                self._slots,
                action,
                distribution_index=distribution_index,
                template_color_map=self.ctx.template_color_map,
                rng=self.rng,
            )
            self._slots = synchronize_effective_slot_fields(
                self._slots, self.ctx.quality_map, self.ctx.trait_map
            )
        self._step_index += 1
        value_after = self.current_value()
        result = RNGStepResult(
            offers=[RNGOffer(**offer.__dict__) for offer in self._last_offers],
            chosen_offer=RNGOffer(**chosen_offer.__dict__),
            value_before=float(value_before),
            value_after=float(value_after),
            delta_value=float(value_after - value_before),
            step_index=int(self._step_index),
            done=self.done(),
        )
        self._last_offers = []
        return result
