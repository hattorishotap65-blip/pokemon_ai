# Parameter Filter Policy

## Overview

| Category | Count | Auto-tune? |
|----------|-------|------------|
| searchable_params | 27 | Yes |
| deny_params | 14 | Never |
| review_required | ~60 | After human review |
| noise (small constants, sentinels) | ~220 | No |

## searchable_params (27)

Safe for staged 30g→50g→200g exploration via auto_tune_pipeline.

### Global (20)

| Name | Current | File |
|------|---------|------|
| zero_damage_attack_penalty | 500.0 | policy.py |
| ko_opponent_bonus | 20.0 | policy.py |
| winning_ko_bonus | 30.0 | policy.py |
| boss_can_ko | 30.0 | policy.py |
| boss_ko_ex | 20.0 | policy.py |
| boss_low_hp | 15.0 | policy.py |
| boss_key_support | 8.0 | policy.py |
| to_active_can_ko | 15.0 | policy.py |
| to_active_can_damage | 5.0 | policy.py |
| alt_attacker_ko_score | 800.0 | damage_predictor.py |
| alt_attacker_damage_score | 400.0 | damage_predictor.py |
| energy_ready_bonus | 200.0 | damage_predictor.py |
| energy_not_ready_penalty | 300.0 | damage_predictor.py |
| ex_final_prize_end_penalty | 400.0 | turn_rule_engine.py |
| ex_final_prize_retreat_boost | 500.0 | turn_rule_engine.py |
| avoid_retreat_losing_energy | 250.0 | turn_rule_engine.py |
| win_condition_weight | 0.6 | evaluator.py |
| deck_critical_penalty | 8.0 | evaluator.py |
| future_weight | 0.7 | planner.py |
| threat_weight | 0.8 | planner.py |

### Deck-specific (7)

| Name | Current | File |
|------|---------|------|
| bellibolt_ability_enables_attack | 280.0 | ionos_rules.py |
| bellibolt_ability_charge | 250.0 | ionos_rules.py |
| bellibolt_ability_progress | 100.0 | ionos_rules.py |
| voltorb_damage_increase | 35.0 | ionos_rules.py |
| voltorb_ko_line | 400.0 | ionos_rules.py |
| bench_low_hp_penalty_per_copy | 15.0 | ionos_rules.py |
| spread_threat_extra_penalty | 20.0 | ionos_rules.py |

## deny_params (14)

Never auto-tune. Safety constraints and card-text constants.

See `configs/params/deny_params.json` for full list and reasons.

## review_required (~60)

Candidates that could be searchable but need human verification first.
Examples: Poffin bench bonuses, energy priority per Pokemon, play_basic scores.
Documented in `docs/parameter_inventory.md`.

## Noise (~220)

Small constants, loop indices, sentinel values, format strings.
Automatically excluded by magnitude filter (|value| < 3.0 and not weight/scale).

## Next Steps

1. Externalize 3-5 searchable_params to data/weights.json
2. Run staged 30g→50g→200g via auto_tune_pipeline
3. Promote review_required to searchable after validation
