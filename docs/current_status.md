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

## Next PR Candidates

1. **damage_predictor.py** — predict attack damage before attacking,
   using weakness/resistance/abilities. Prevent 0-damage attacks (e.g.
   Bellibolt ex vs Crustle with prevent-damage-from-ex).
2. **Bellibolt ability timing** — evaluate whether Bellibolt ability (energy
   acceleration) is used at optimal timing
3. **Boss's Orders targeting** — improve target selection when playing Boss

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
