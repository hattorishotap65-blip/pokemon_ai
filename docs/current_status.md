# Current Status

Last updated: 2026-06-22

## Submission

| Item | Value |
|------|-------|
| Version | v5 (AGENT_VERSION in main.py) |
| Deck | Iono's Kilowattrel |
| Base commit | `9f3101d` |
| Submission PR | #86 |
| Runtime | Startup confirmed |

## Key Files

| File | Role |
|------|------|
| `main.py` | Observation normalization, option enrichment, action selection, logging |
| `agent/policy.py` | Base scoring, action type evaluation, integrates turn_plan/ionos_rules/turn_rule_engine |
| `agent/ionos_rules.py` | Iono deck-specific rules: Bellibolt/Voltorb/Kilowattrel/Poffin/energy |
| `agent/turn_rule_engine.py` | Attack/retreat/end/ability safety guards, empty bench, winning attack, final prize |
| `agent/turn_plan.py` | KO plan, pre-attack requirements (energy/switch/boss) |
| `agent/opponent_model.py` | Opponent threat evaluation |
| `agent/effect_engine.py` | Card effect scoring, damage estimation |
| `agent/evaluator.py` | Board state evaluation |
| `agent/planner.py` | Lookahead strategy |
| `data/weights.json` | Externalized scoring weights |
| `experiments/test_turn_rule_engine.py` | 90 tests for turn rule safety guards |
| `experiments/test_bench_liability.py` | 17 tests for bench liability rules |

## Active Weights

| Weight | Value | Status |
|--------|-------|--------|
| retreat_to_better_attacker_bonus | 1400.0 | adopted (PR #30) |
| attack_suppress_penalty | -40.0 | adopted (PR #39) |
| energy_attack_enablement_bonus | 200.0 | adopted (PR #63) |
| legal_attack_score | 250.0 | adopted (PR #75) |
| voltorb_ko_attack_bonus | 1000.0 | confirmed (PR #56) |
| voltorb_damage_scaling | 0.8 | confirmed (PR #58) |
| evolve_first_bellibolt_bonus | 220.0 | confirmed (PR #69) |
| evolve_first_kilowattrel_bonus | 7.0 | confirmed (PR #71) |

## Active Safety Guards

| Guard | PR | Status |
|-------|-----|--------|
| Empty bench loss prevention | #80 | active |
| Final prize ex survival | #80 | active |
| Winning attack guard | #82 | active |
| Low HP bench liability | #83 | active |
| Spread threat detection | #83 | active |
| Poffin diversity | #83 | active |

## Critical Fix: Normalized State Compatibility

**ISSUE:** `turn_rule_engine.py` helpers assumed `state["players"]` format,
but `main.py._board_to_state()` returns normalized format with
`active_pokemon`/`bench` at top level. All safety guards (#80/#82/#83)
were NOT firing in production.

**FIX:** `get_own_active`/`get_own_bench` now handle both formats.
`get_card_name` falls back to `card_id` lookup via `cg.api`.
First call to `cg.api.all_card_data()` populates `_CARD_NAME_CACHE`;
subsequent lookups are O(1) dict access.

## Smoke Check (post-fix, normalized state)

| Metric | Value |
|--------|-------|
| Games | 18 |
| anomalies/g | 4.56 |
| Errors | 0 |
| Safety | all 0 |

## Smoke Check (post card metadata enrichment)

| Metric | Value |
|--------|-------|
| Games | 30 |
| anomalies/g | 6.33 |
| Errors | 0 |
| Timeouts | 0 |
| Safety | all 0 |
| Avg time/game | 3180ms |
| Speed regression | None |

## Known Limitations

- Winning attack guard: own prizes=2 + attack can KO ex may still be
  outweighed by retreat boost in some scoring layers
- Spread threat detection: name-based only (Dragapult/Greninja/Incineroar)
- Bench liability: does not account for opponent's actual damage output

## Card Metadata Enrichment (PR #89)

`_normalize_pokemon` now calls `enrich_pokemon()` from `agent/card_metadata.py`.
All active/bench Pokemon (own + opponent) get enriched with:
name, is_ex, is_basic, stage, weakness, resistance, attacks, abilities, retreat_cost.
Cached via `_CARD_CACHE`/`_ATTACK_CACHE`. Graceful degradation if cg.api unavailable.

## Damage Predictor (PR #90)

`agent/damage_predictor.py`: predicts attack damage before attacking.
- `prevent_damage_from_ex` detection via ability text keywords
- Weakness (x2) and resistance (-30) applied
- Iono deck card-specific damage via effect_engine fallback
- `policy.py._score_attack` penalizes 0-damage attacks by -500

30g smoke (post-fix, latest head 1e3df1a): 6.53/g, 0 errors, 0 timeouts,
safety all 0, 3428ms/game. No regressions.

## Alternative Attacker Selection (PR #91)

`find_alternative_attackers()` in damage_predictor.py: when active attack
predicts 0 damage, searches bench for candidates that can damage the defender.
Scores by can_ko > can_damage > non_ex > energy_ready > HP.
policy.py retreat scored +8/+12 when alternative found, to_active uses
predicted damage for switch target selection. No opponent-name logic.

30g smoke: 4.83/g, 0 errors, safety all 0, 2991ms/game.

## Stable Candidate Validation (150g)

| Metric | Value |
|--------|-------|
| Games | 150 |
| Anomalies/g | 5.12 |
| Errors | 0 |
| Timeouts | 0 |
| attack_available_but_no_attack | 0 |
| end_when_attack_available | 0 |
| retreat_when_attack_available | 0 |
| ability_without_followup_attack | 0 |
| Tests | 313/313 |
| Avg time/game | ~4300ms |

Included PRs since v3: #88 (normalized state fix), #89 (card metadata),
#90 (damage predictor), #91 (alternative attacker), #92 (Boss targeting),
#93 (energy readiness), #94 (Bellibolt ability timing).

**Verdict: Ready for submission.**

## Core Parameter Search (PR #100-#102)

Externalized 5 core params to `configs/params/default_params.json`.
Searched via `scripts/run_core_param_search.py` at 30g/50g/100g/200g.

| Parameter | Tested Range | Best 30g | 50g | 100g | 200g | Result |
|-----------|-------------|----------|-----|------|------|--------|
| zero_damage_attack_penalty | 200-800 | 500 (=BL) | - | - | - | 500 confirmed |
| ko_opponent_bonus | 10-40 | 20 (=BL) | - | - | - | 20 confirmed |
| boss_can_ko | 15-50 | 30 (=BL) | - | - | - | 30 confirmed |
| alt_attacker_ko_score | 400-1200 | 1200 (-7%) | 1200 (-4%) | 1200 (-10%) | 1200 (-0.6%) | 800 confirmed |
| energy_ready_bonus | 100-400 | 100 (-11%) | 100 (+2%) | - | - | 200 confirmed |

**Conclusion:** All 5 core params confirmed at current values.
alt_attacker_ko_score=1200 showed improvement at 30g/100g but vanished at 200g.
energy_ready_bonus=100 improved at 30g but reversed at 50g.

## Attack Plan Validation (PR #104/#105)

Lightweight attack_plan with Iono-specific plan types.
30g + 50g + 100g validation after merge:

| Scale | Games | Errors | Timeouts | APG | Safety | ms/game |
|-------|-------|--------|----------|-----|--------|---------|
| 30g | 30 | 0 | 0 | - | all 0 | 2938 |
| 50g | 50 | 0 | 0 | - | all 0 | 3583 |
| 100g | 100 | 0 | 0 | 5.68 | all 0 | 3113 |

Tests: 460/460 pass.

**Verdict: stable.** APG 5.68 vs pre-plan 5.12 is within 30g variance.
No safety regressions. Speed maintained (~3100ms/game).

## Next PR Candidates

1. Deck-out risk awareness when deck_count is low
2. Attack plan cache (avoid re-generating per action)

## Rejected/Confirmed Parameters

| Parameter | Tested | Result |
|-----------|--------|--------|
| advantage_weight | 0.2-0.6 | 0.4 confirmed |
| energy_to_plan_bonus | 3-8 | 5.0 confirmed |
| energy_to_plan_bonus_no_need | 1-4 | 2.0 confirmed |
| voltorb_ko_attack_bonus | 500-1500 | 1000.0 confirmed |
| voltorb_damage_scaling | 0.4-1.2 | 0.8 confirmed |
| evolve_first_bellibolt_bonus | 110-330 | 220.0 confirmed |
| evolve_first_kilowattrel_bonus | 3.5-14 | 7.0 confirmed |
| legal_attack_score | 75-250 | 250.0 adopted |
| energy_attack_enablement_bonus | 150-500 | 200.0 adopted |
| zero_damage_attack_penalty | 200-800 | 500 confirmed |
| ko_opponent_bonus | 10-40 | 20 confirmed |
| boss_can_ko | 15-50 | 30 confirmed |
| alt_attacker_ko_score | 400-1200 | 800 confirmed |
| energy_ready_bonus | 100-400 | 200 confirmed |
