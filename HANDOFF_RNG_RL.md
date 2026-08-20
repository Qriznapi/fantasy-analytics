# RNG Actor-Critic Handoff

## Current objective

Improve Dota Fantasy reroll recommendations without changing the exact game
rules or promoting a model without a matched evaluation.

Project root:

```text
D:\Codex\2026-08-05\referenced-chatgpt-conversation-this-is-an\work\project-f
```

## Current baseline

- Database: `data/ti_2026_fantasy_compact.sqlite`
- Profile: `ti2026_playoff_observed_nothingtogay_v1`
- Baseline actor: `models/rng_neural_slot_selfplay_selected_v1.pt`
- Production recommendation mechanism: actor-assisted Monte Carlo planner.
- Canonical environment: `src/fantasy_rng_env.py`
- Planner: `src/fantasy_rng_slot_planner.py`

The actor proposes legal `token + role` actions; the planner evaluates top
candidates plus refresh by exact simulated rollouts. A new model is never
promoted automatically.

## Rule invariants

1. Every turn has three token IDs plus optional refresh.
2. A selected token is applied to one selected role; then the next three
   tokens are sampled again.
3. No duplicate stat names are allowed within a role.
4. Stat rerolls cannot reproduce the replaced stat or another stat in role.
5. Quality rerolls respect tier bounds and cannot return the previous tier.
6. `quality_shift_plus1` and `quality_shift_plus2_minus1` follow their exact
   multi-slot constraints.

## Latest rejected experiment

Stage 2 produced a single shared actor-critic checkpoint:

- actor head: KL-constrained planner behaviour distillation;
- Q head: normalized realized terminal banner value for chosen planner action;
- V head: auxiliary value prediction;
- planner: bounded actor-weighted Q leaf bootstrap, disabled by default.

Output:

- corpus: `rng_offline_planner_trajectory_stage2_actor_critic_v1`;
- merged corpus: `rng_offline_planner_trajectory_stage2_actor_critic_combined_v1`;
- artifact: `models/rng_neural_slot_actor_critic_stage2_v1.pt`;
- matched report: `reports/rng_neural_slot_actor_critic_stage2_v1_evaluation.json`.

The run added 300 fresh 30-step teacher episodes to the 360 Stage-1 episodes
and trained 48 epochs. It is rejected, not a current candidate:

- actor-only matched delta: `-519`, CI `[-1621; +527]`;
- actor-critic matched delta: `-369`, CI `[-1560; +735]`;
- fresh safe-router delta: `-2,922`, CI `[-4,928; -1,288]`.

## Promotion rule

Keep `models/rng_neural_slot_selfplay_selected_v1.pt + planner` as the active
system. A future critic needs genuine per-state alternative-action terminal
labels before it is reconsidered.

## Documentation

Use `docs/README.md` as the only project documentation index. Historical
scorecards and old RL roadmaps were intentionally removed to avoid conflicting
architecture descriptions.
