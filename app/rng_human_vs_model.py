from __future__ import annotations

import sys
import secrets
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantasy_rng_env import RNGEnvironment, RNGOffer, RNGTokenOffer
from fantasy_rng_slot_planner import choose_planned_action
from fantasy_rng_slot_rl import load_slot_model
from fantasy_rng_screenshot_ocr import parse_fantasy_screenshot


DB_PATH = ROOT / "data" / "ti_2026_fantasy_compact.sqlite"
MODEL_PATH = ROOT / "models" / "rng_neural_slot_selfplay_selected_v1.pt"
TOKEN_PRESET = ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json"
STARTER_PRESET = ROOT / "configs" / "rng_initial_states" / "starters_conservative_v4.json"
PROFILE_ID = "ti2026_playoff_observed_nothingtogay_v1"
ADVISOR_ROLLOUTS = 6
ADVISOR_HORIZON = 8


def inject_css() -> None:
    st.markdown("""<style>
    .stApp { background: radial-gradient(circle at 15% 5%, #33290f 0, #15120b 34%, #080807 82%); color: #eee0b4; }
    [data-testid='stHeader'] { background: transparent; }
    .block-container { padding-top: 1rem; padding-bottom: .7rem; max-width: 1600px; }
    h1 { font-family: Georgia,serif!important; font-size:2rem!important; color:#f5d67c!important; margin:0!important; }
    .banner { border: 1px solid #8b6d2e; border-top: 3px solid #d8b24e; background: linear-gradient(145deg,#28200f,#120f0a); padding: 13px; min-height: 390px; box-shadow: 0 8px 25px #0008; }
    .role-title { color:#f8db82; font-family: Georgia, serif; font-size: 1.18rem; letter-spacing: .09em; text-align:center; margin-bottom: 8px; }
    .slot { border-left: 5px solid #6a5960; background:#211b17; margin:7px 0; padding:8px 9px; font-size:.8rem; line-height:1.2; transition:.15s; }
    .slot.red { border-left-color:#c94b49; }.slot.green { border-left-color:#4d9b62; }.slot.blue { border-left-color:#597dcc; }
    .slot.target { background:#504019; outline:1px solid #f6ce55; transform:translateX(3px); }
    .slot.possible { background:#30291b; outline:1px dashed #c7a65b; }
    .muted { color:#a99b7c; font-size:.74rem; }.score { color:#f8d272; font-size:1.28rem; font-weight:700; }
    .token-note { color:#dfc77f; background:#20190e; border:1px solid #6b5420; padding:7px 10px; min-height:38px; font-size:.8rem; }
    .model-panel { border-color:#3d6b96; border-top-color:#62a7d9; }.model-panel .role-title { color:#9ddcff; }
    [data-testid='stVerticalBlockBorderWrapper'] { padding: .35rem .6rem; }
    </style>""", unsafe_allow_html=True)


def fresh_game(seed: int, objective: str) -> None:
    model, artifact = load_slot_model(MODEL_PATH)
    model.eval()
    common = dict(profile_id=PROFILE_ID, db_path=DB_PATH, preset_path=TOKEN_PRESET, initial_state_preset_path=STARTER_PRESET, objective_mode=objective, max_steps=30)
    st.session_state.model = model
    st.session_state.artifact = artifact
    st.session_state.policy_label = "Baseline actor + planner"
    st.session_state.critic_leaf_weight = 0.0
    st.session_state.human = RNGEnvironment(**common, seed=seed)
    st.session_state.opponent = RNGEnvironment(**common, seed=seed)
    st.session_state.schedule = RNGEnvironment(**common, seed=seed + 9_999)
    st.session_state.human.reset(seed=seed)
    st.session_state.opponent.reset(seed=seed)
    st.session_state.tokens = st.session_state.schedule.sample_token_offers()
    st.session_state.last_model = "Waiting for the first guided planner move."
    st.session_state.history = []
    st.session_state.selected_role = "core"
    st.session_state.advisor_result = None


def token_offer_from_id(env: RNGEnvironment, token_id: str) -> RNGTokenOffer:
    action = next(item for item in env._action_specs if str(item.get("token_id", item["token_type"])) == token_id)
    return RNGTokenOffer(
        token_id=token_id, token_type=str(action["token_type"]),
        action_scope=str(action.get("action_scope", "slot")), target_color_group=str(action.get("target_color_group", "")),
        offer_weight=float(action.get("offer_weight", 1.0)),
    )


def merge_complete_ocr_roles(current_slots: list[dict], parsed: dict) -> tuple[list[dict], list[str]]:
    """Apply only whole, fully parsed roles; retain uncertain roles unchanged."""
    merged = [dict(row) for row in current_slots]
    applied: list[str] = []
    for role, items in parsed["roles"].items():
        if len(items) != 5 or any(not {"stat_name", "quality_tier", "trait_name"}.issubset(item) for item in items):
            continue
        by_index = {int(row["slot_index"]): row for row in merged if row["role_scope"] == role}
        for index, item in enumerate(items, start=1):
            by_index[index].update(item)
        applied.append(role)
    return merged, applied


def advisor_recommendation(env: RNGEnvironment, tokens: list[RNGTokenOffer]) -> dict:
    offers = [action for token in tokens for action in env.legal_actions_for_token(token.token_id)]
    offers.append(RNGOffer("refresh_offers", "refresh_offers", "refresh_offers", "global", -1, "", "", "", 0.0, 1.0, True))
    decision = choose_planned_action(
        st.session_state.model, st.session_state.artifact, env, offers,
        top_k=3, rollouts=ADVISOR_ROLLOUTS, horizon=min(ADVISOR_HORIZON, env.steps_remaining()), risk_mode=env.objective_mode,
        seed=env.seed + env.steps_remaining(), include_refresh_candidate=True,
        preference_weight=0.10, strategy_prior_weight=1.0,
        critic_leaf_weight=st.session_state.get("critic_leaf_weight", 0.0),
    )
    chosen = next(item for item in decision["candidates"] if int(item["action_index"]) == int(decision["chosen_action_index"]))
    return {"offer": offers[int(decision["chosen_action_index"])], "chosen": chosen}


def targeted_slots(action: RNGOffer, slots: list[dict]) -> tuple[set[tuple[str, int]], bool]:
    if action.is_refresh_action:
        return set(), False
    eligible = [slot for slot in slots if slot["role_scope"] == action.role_scope and (not action.target_color_group or slot["color_group"] == action.target_color_group)]
    if not eligible:
        return set(), False
    scope = action.action_scope
    if "all" in scope:
        return {(slot["role_scope"], int(slot["slot_index"])) for slot in eligible}, False
    if "random" in scope:
        return {(slot["role_scope"], int(slot["slot_index"])) for slot in eligible}, True
    if "first" in scope:
        chosen = min(eligible, key=lambda slot: int(slot["slot_index"]))
    elif "last" in scope:
        chosen = max(eligible, key=lambda slot: int(slot["slot_index"]))
    else:
        chosen = eligible[0]
    return {(chosen["role_scope"], int(chosen["slot_index"]))}, False


def banner_html(env: RNGEnvironment, title: str, *, action: RNGOffer | None = None, model: bool = False) -> str:
    targets, possible = targeted_slots(action, env.state_slots()) if action else (set(), False)
    groups = [("core", "CORE"), ("mid", "MID"), ("support", "SUPPORT")]
    columns = []
    for role, label in groups:
        cards = []
        for slot in sorted((slot for slot in env.state_slots() if slot["role_scope"] == role), key=lambda item: int(item["slot_index"])):
            key = (role, int(slot["slot_index"]))
            extra = " target" if key in targets and not possible else " possible" if key in targets else ""
            cards.append(f"<div class='slot {slot['color_group']}{extra}'><b>{slot['stat_name'].replace('_', ' ').upper()}</b><br><span class='muted'>{slot['quality_tier']} · {slot['trait_name']} · x{float(slot['multiplier']):.2f}</span></div>")
        columns.append(f"<div style='width:33%;display:inline-block;vertical-align:top;padding:0 4px'><div class='role-title'>{label}</div>{''.join(cards)}</div>")
    klass = "banner model-panel" if model else "banner"
    return f"<div class='{klass}'><div class='role-title'>{title}</div><div class='score'>Score: {env.current_value():,.0f}</div><div class='muted'>Rolls remaining: {env.steps_remaining()}</div><hr style='border-color:#655020'>{''.join(columns)}</div>"


def hover_preview(tokens: list[object], env: RNGEnvironment) -> None:
    """Interactive preview: hovering a token highlights its exact mutable field."""
    slots = env.state_slots()
    def field_for(token: object) -> str:
        return "stat" if "stat" in token.token_type else "quality" if "quality" in token.token_type else "trait" if "trait" in token.token_type else "emblem"

    role_html = []
    for role, label in (("core", "CORE"), ("mid", "MID"), ("support", "SUPPORT")):
        cards = []
        for slot in sorted((row for row in slots if row["role_scope"] == role), key=lambda row: int(row["slot_index"])):
            key = f"{role}-{slot['slot_index']}"
            cards.append(f"""<div class='slot {slot['color_group']}'><div class='slot-head'>#{slot['slot_index']} · {slot['color_group'].upper()}</div>
                <div class='field stat' data-key='{key}-stat'>{slot['stat_name'].replace('_', ' ').upper()}</div>
                <div class='field quality' data-key='{key}-quality'>{slot['quality_tier']}</div><div class='field trait' data-key='{key}-trait'>{slot['trait_name']}</div>
                <small>x{float(slot['multiplier']):.2f}</small></div>""")
        role_html.append(f"<div class='role'><div class='role-name'>{label}</div>{''.join(cards)}</div>")
    token_html = []
    for token in tokens:
        field = field_for(token)
        possible = []
        # Token offers carry a generic scope for sampling.  The concrete action
        # rows retain the true first/last slot index, so use those rows rather
        # than reconstructing a target from the generic token description.
        for action in env.legal_actions_for_token(token.token_id):
            eligible = [slot for slot in slots if slot["role_scope"] == action.role_scope and (not action.target_color_group or slot["color_group"] == action.target_color_group)]
            if action.slot_index > 0:
                chosen = [slot for slot in eligible if int(slot["slot_index"]) == action.slot_index]
            else:
                chosen = eligible
            possible.extend(f"{slot['role_scope']}-{slot['slot_index']}-{field}" for slot in chosen)
        label = "STAT" if field == "stat" else "TIER" if field == "quality" else "TRAIT" if field == "trait" else "EMBLEM"
        token_html.append(f"<div class='token' data-targets='{','.join(possible)}' onmouseenter=\"highlight(this.dataset.targets)\" onmouseleave=\"clearHighlight()\"><b>{token.token_id}</b><br><small>hover preview: {label} · {token.action_scope}</small></div>")
    components.html(f"""<style>
        body{{margin:0;background:#17120a;color:#eee0b4;font-family:Georgia,serif}} .wrap{{padding:12px;border:1px solid #80642a}}
        .tokens{{display:flex;gap:10px;margin-bottom:12px}} .token{{flex:1;background:linear-gradient(135deg,#38230f,#1c130b);color:#f1d281;border:1px solid #987330;padding:12px;cursor:help;text-align:left;font-size:14px}}
        .token:hover{{background:linear-gradient(135deg,#604019,#26180d);border-color:#f4ca52}} .roles{{display:flex;gap:8px}}
        .role{{flex:1}} .role-name{{text-align:center;color:#f4d67e;letter-spacing:.12em;font-size:15px;margin:3px 0 8px}} .slot{{background:#251c15;border-left:5px solid #777;margin:6px 0;padding:8px;font-size:12px;line-height:1.3}} .red{{border-color:#c94b49}} .green{{border-color:#4d9b62}} .blue{{border-color:#597dcc}}
        .slot-head,small{{color:#a99b7c;font-size:10px}} .field{{display:inline-block;margin:4px 4px 0 0;padding:3px 5px;border:1px solid transparent;transition:.12s}} .stat{{color:#f1dcc0}} .quality{{color:#bcd4ff}} .trait{{color:#b8dfae}}
        .hot{{background:#6b4e16!important;color:#fff2ba!important;border-color:#ffd55c!important;box-shadow:0 0 9px #e5ae3b88}}
        </style><div class='wrap'><div class='tokens'>{''.join(token_html)}</div><div class='roles'>{''.join(role_html)}</div></div>
        <script>function clearHighlight(){{document.querySelectorAll('.field').forEach(x=>x.classList.remove('hot'))}} function highlight(keys){{let active=new Set(keys.split(','));document.querySelectorAll('.field').forEach(x=>x.classList.toggle('hot',active.has(x.dataset.key)))}}</script>""", height=470)


def apply_human_move(token_index: int, role: str | None) -> None:
    human, opponent, tokens = st.session_state.human, st.session_state.opponent, st.session_state.tokens
    if token_index == len(tokens):
        human_action = RNGOffer("refresh_offers", "refresh_offers", "refresh_offers", "global", -1, "", "", "", 0.0, 1.0, True)
    else:
        actions = human.legal_actions_for_token(tokens[token_index].token_id)
        human_action = next(action for action in actions if action.role_scope == role)
    opponent_actions = [action for token in tokens for action in opponent.legal_actions_for_token(token.token_id)]
    opponent_actions.append(RNGOffer("refresh_offers", "refresh_offers", "refresh_offers", "global", -1, "", "", "", 0.0, 1.0, True))
    # A game decision is three offered token IDs plus Refresh.  The planner
    # must not replace one offered token with another role-target of the same
    # token while constructing its candidate set.
    decision = choose_planned_action(
        st.session_state.model, st.session_state.artifact, opponent, opponent_actions,
        top_k=3, rollouts=ADVISOR_ROLLOUTS, horizon=min(ADVISOR_HORIZON, opponent.steps_remaining()),
        risk_mode=opponent.objective_mode, seed=opponent.seed + opponent.steps_remaining(),
        include_refresh_candidate=True, preference_weight=0.10, strategy_prior_weight=1.0,
        critic_leaf_weight=st.session_state.get("critic_leaf_weight", 0.0),
    )
    model_action = opponent_actions[int(decision["chosen_action_index"])]
    human_result = human.step_action(human_action)
    opponent_result = opponent.step_action(model_action)
    chosen = next(row for row in decision["candidates"] if int(row["action_index"]) == int(decision["chosen_action_index"]))
    reasons = ", ".join(chosen.get("strategy_prior_reasons", [])) or "value rollout"
    st.session_state.last_model = f"{model_action.token_id} -> {model_action.role_scope}; {opponent_result.delta_value:+.0f} points; {reasons}"
    st.session_state.history.append({"step": human_result.step_index, "human": f"{human_action.token_id} -> {human_action.role_scope}", "model": st.session_state.last_model})
    if not human.done():
        st.session_state.tokens = st.session_state.schedule.sample_token_offers()


def main() -> None:
    st.set_page_config(page_title="Fantasy Banner Lab", layout="wide")
    inject_css()
    if "ui_seed" not in st.session_state:
        st.session_state.ui_seed = 2026
    header, seed_box, objective_box, reset_box, random_box = st.columns([4, 1, 1.2, 1.25, 1.25], vertical_alignment="bottom")
    with header:
        st.title("Fantasy Banner Lab")
        st.caption("Guided planner versus you. It combines rollouts with the strategic reroll priority plan.")
    with seed_box:
        seed = st.number_input("Seed", step=1, label_visibility="visible", key="ui_seed")
    with objective_box:
        objective = st.selectbox("Risk", ["balanced", "safe", "ceiling"], index=0)
    with reset_box:
        reset = st.button("New session", use_container_width=True)
    with random_box:
        random_start = st.button("Random start", use_container_width=True, on_click=lambda: st.session_state.__setitem__("ui_seed", secrets.randbelow(2_000_000_000)))
    if reset or random_start or "human" not in st.session_state:
        fresh_game(int(seed), objective)
        st.rerun()
    if st.session_state.human.done():
        human_score = st.session_state.human.current_value(); model_score = st.session_state.opponent.current_value()
        st.success(f"Final: You {human_score:,.0f} vs Model {model_score:,.0f}. {'You win.' if human_score > model_score else 'Model wins.'}")
        return
    tokens = st.session_state.tokens
    st.caption(f"Active policy: {st.session_state.policy_label}")
    st.markdown("<div class='token-note'><b>1.</b> Select a role. <b>2.</b> Click a token to apply it immediately. Hover the preview cards below to see the exact field that will change.</div>", unsafe_allow_html=True)
    role = st.radio("Target role", ["core", "mid", "support"], horizontal=True, key="selected_role", format_func=lambda value: value.upper())
    token_columns = st.columns(len(tokens) + 1)
    clicked_token: int | None = None
    for index, token in enumerate(tokens):
        changed = "STAT" if "stat" in token.token_type else "TIER" if "quality" in token.token_type else "TRAIT" if "trait" in token.token_type else "EMBLEM"
        label = f"{token.token_id.replace('_', ' ').upper()}\n{changed} · {token.target_color_group.upper() or 'ANY'}"
        with token_columns[index]:
            if st.button(label, key=f"apply_token_{index}", type="primary", use_container_width=True):
                clicked_token = index
    with token_columns[-1]:
        if st.button("REFRESH\nSkip this offer", key="refresh_offers", use_container_width=True):
            clicked_token = len(tokens)
    left, right = st.columns([2.45, 1.55], gap="medium")
    with left:
        st.markdown(f"<div class='token-note'><b>YOUR BANNER</b> &nbsp; Score: <b>{st.session_state.human.current_value():,.0f}</b> &nbsp; · &nbsp; Rolls remaining: <b>{st.session_state.human.steps_remaining()}</b></div>", unsafe_allow_html=True)
        hover_preview(tokens, st.session_state.human)
    with right:
        st.markdown(banner_html(st.session_state.opponent, "MODEL BANNER", model=True), unsafe_allow_html=True)
        st.info(f"Model last move: {st.session_state.last_model}")
    if clicked_token is not None:
        apply_human_move(clicked_token, role)
        st.rerun()
    if st.session_state.get("history"):
        with st.expander("Recent moves", expanded=False):
            st.dataframe(st.session_state.history[-10:][::-1], use_container_width=True, hide_index=True)

    with st.expander("Client advisor: enter the live banner and three offered tokens", expanded=False):
        st.caption("This does not alter the official client. Transcribe its current 15 emblems here, then ask for a recommendation.")
        screenshot = st.file_uploader("Optional: upload a client screenshot (PNG/JPG)", type=["png", "jpg", "jpeg"], key="client_screenshot")
        if screenshot and st.button("Read screenshot locally", key="read_client_screenshot"):
            try:
                parsed = parse_fantasy_screenshot(screenshot.getvalue())
                st.session_state.screenshot_parse = parsed
                if len(parsed["tokens"]) == 3 and len(set(parsed["tokens"])) == 3:
                    # The three OCR suggestions become the editable default;
                    # the user can still correct any uncertain token before
                    # requesting a recommendation.
                    st.session_state.client_offer_ids = parsed["tokens"]
                merged_slots, applied_roles = merge_complete_ocr_roles(st.session_state.human.state_slots(), parsed)
                if applied_roles:
                    st.session_state.human.set_state_slots(merged_slots)
                    st.session_state.opponent.set_state_slots(merged_slots)
                    if parsed["roll_tokens_remaining"] is not None:
                        st.session_state.client_remaining_tokens = parsed["roll_tokens_remaining"]
                        st.session_state.human.set_steps_remaining(parsed["roll_tokens_remaining"])
                        st.session_state.opponent.set_steps_remaining(parsed["roll_tokens_remaining"])
                    st.session_state.advisor_result = None
                    if parsed["complete"]:
                        st.success("Screenshot banner loaded. Review the table and token suggestions below before requesting advice.")
                    else:
                        st.warning(f"Loaded complete OCR roles: {', '.join(applied_roles)}. Manually correct: {', '.join(parsed['incomplete_roles'])}.")
                else:
                    st.warning(f"OCR needs manual correction for: {', '.join(parsed['incomplete_roles'])}.")
            except RuntimeError as exc:
                st.error(str(exc))
        parsed = st.session_state.get("screenshot_parse")
        if parsed:
            coverage = " | ".join(
                f"{role}: {len(parsed['roles'].get(role, []))}/5"
                for role in ("core", "mid", "support")
            )
            st.caption(f"OCR emblem coverage: {coverage}. Only complete 5/5 roles are applied automatically.")
            st.caption(f"OCR token suggestions: {', '.join(parsed['tokens']) or 'none'}")
            st.caption(f"OCR button text: {' | '.join(text or '?' for text in parsed['token_button_texts'])}")
            if parsed["roll_tokens_remaining"] is not None:
                st.caption(f"OCR remaining roll tokens: {parsed['roll_tokens_remaining']}")
            for note in parsed["notes"]:
                st.caption(f"Review: {note}")
        if "client_remaining_tokens" not in st.session_state:
            st.session_state.client_remaining_tokens = st.session_state.human.steps_remaining()
        remaining_tokens = st.number_input("Remaining roll tokens", min_value=0, max_value=30, step=1, key="client_remaining_tokens")
        editable = pd.DataFrame(st.session_state.human.state_slots())[["role_scope", "slot_index", "stat_name", "quality_tier", "trait_name"]]
        edited = st.data_editor(
            editable, key="client_banner_editor", hide_index=True, use_container_width=True,
            disabled=["role_scope", "slot_index"], num_rows="fixed",
            column_config={
                "quality_tier": st.column_config.SelectboxColumn("quality_tier", options=["tier_i", "tier_ii", "tier_iii", "tier_iv", "tier_v"]),
                "trait_name": st.column_config.SelectboxColumn("trait_name", options=["fractal", "benevolent", "vampiric", "unique", "friendly"]),
            },
        )
        if st.button("Load this client banner", key="load_client_banner"):
            rows = edited.to_dict(orient="records")
            try:
                st.session_state.human.set_state_slots(rows)
                st.session_state.opponent.set_state_slots(rows)
                st.session_state.human.set_steps_remaining(int(remaining_tokens))
                st.session_state.opponent.set_steps_remaining(int(remaining_tokens))
                st.session_state.advisor_result = None
                st.success("Client banner loaded into the advisor.")
            except ValueError as exc:
                st.error(str(exc))
        token_options = sorted({str(item.get("token_id", item["token_type"])) for item in st.session_state.human._action_specs})
        if "client_offer_ids" not in st.session_state:
            st.session_state.client_offer_ids = [token.token_id for token in tokens]
        custom_ids = st.multiselect("The three offered token IDs", token_options, max_selections=3, key="client_offer_ids")
        if st.button("Get guided recommendation", key="get_client_recommendation"):
            if len(custom_ids) != 3 or len(set(custom_ids)) != 3:
                st.error("Select exactly three distinct token IDs.")
            else:
                st.session_state.human.set_steps_remaining(int(remaining_tokens))
                st.session_state.opponent.set_steps_remaining(int(remaining_tokens))
                st.session_state.advisor_result = advisor_recommendation(st.session_state.human, [token_offer_from_id(st.session_state.human, token_id) for token_id in custom_ids])
        result = st.session_state.get("advisor_result")
        if result:
            offer, chosen = result["offer"], result["chosen"]
            action = "REFRESH" if offer.is_refresh_action else f"{offer.token_id} -> {offer.role_scope.upper()}"
            reasons = ", ".join(chosen.get("strategy_prior_reasons", [])) or "rollout value"
            st.success(f"Recommendation: {action}. Reason: {reasons}.")


if __name__ == "__main__":
    main()
