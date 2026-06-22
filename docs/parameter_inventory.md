# Parameter Inventory

Last updated: 2026-06-22

## Summary

| Category | Count | Searchable |
|----------|-------|------------|
| global_params | 55 | 42 |
| deck_params | 38 | 35 |
| fixed_rules | 8 | 0 |
| **Total** | **101** | **77** |

Already externalized in data/weights.json: 11 weights

---

## global_params

Values shared across decks. Candidates for auto_tune_pipeline.

### Attack Scoring (policy.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 10.0 | policy:421 | base_attack_score | yes | 5-20 |
| 500.0 | policy:449 | zero_damage_attack_penalty | yes | 200-800 |
| 20.0 | policy:458 | ko_opponent_bonus | yes | 10-40 |
| 30.0 | policy:461 | winning_ko_bonus | yes | 15-50 |
| 5.0 | policy:464 | almost_ko_bonus | yes | 2-10 |

### Retreat Scoring (policy.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 8.0/12.0 | policy:726-728 | retreat_to_alt_attacker | yes | 5-20 |
| 7.0 | policy:729 | retreat_save_pokemon | yes | 4-12 |
| 3.5 | policy:730 | retreat_low_hp | yes | 2-6 |
| 1.0 | policy:731 | retreat_unnecessary | no | - |

### Boss's Orders Targeting (policy.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 30.0 | policy:948 | boss_can_ko | yes | 15-50 |
| 20.0 | policy:951 | boss_ko_ex | yes | 10-40 |
| 15.0 | policy:964 | boss_low_hp | yes | 8-25 |
| 5.0 | policy:967 | boss_moderate_hp | yes | 2-10 |
| 8.0 | policy:973 | boss_key_support | yes | 4-15 |

### Switch Target (policy.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 15.0 | policy:1012 | to_active_can_ko | yes | 8-25 |
| 5.0 | policy:1014 | to_active_can_damage | yes | 2-10 |
| 10.0 | policy:1016 | to_active_zero_damage_penalty | yes | 5-20 |

### Damage Target (policy.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 50.0 | policy:1117 | damage_target_ko | yes | 25-80 |
| 20.0 | policy:1122 | damage_target_low_hp_40 | yes | 10-30 |
| 10.0 | policy:1126 | damage_target_low_hp_80 | yes | 5-20 |
| 15.0 | policy:1132 | damage_target_main_attacker | yes | 8-25 |
| 10.0 | policy:1138 | damage_target_ex | yes | 5-20 |

### Alternative Attacker (damage_predictor.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 800.0 | predictor:203 | alt_attacker_ko_score | yes | 400-1200 |
| 400.0 | predictor:206 | alt_attacker_damage_score | yes | 200-600 |
| 100.0 | predictor:210 | non_ex_bonus | yes | 50-200 |
| 200.0 | predictor:214 | energy_ready_bonus | yes | 100-400 |
| 300.0 | predictor:217 | energy_not_ready_penalty | yes | 150-500 |

### Turn Rules (turn_rule_engine.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 400.0 | engine:457 | ex_final_prize_end_penalty | yes | 200-600 |
| 500.0 | engine:459 | ex_final_prize_retreat_boost | yes | 300-800 |
| 60.0 | engine:468 | avoid_end_ability_available | yes | 30-100 |
| 250.0 | engine:475 | avoid_retreat_losing_energy | yes | 100-400 |
| 40.0 | engine:476 | retreat_low_priority | yes | 20-80 |
| 15.0 | engine:484 | ability_can_continue | yes | 8-25 |
| 10.0 | engine:490 | attach_can_continue | yes | 5-20 |

### Evaluator (evaluator.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 0.6 | evaluator:8 | win_condition_weight | yes | 0.3-1.0 |
| 8.0 | evaluator:92 | deck_critical_penalty | yes | 4-15 |
| 3.0 | evaluator:94 | deck_low_penalty | yes | 1-6 |

### Planner (planner.py)

| Value | Location | Role | Search? | Range |
|-------|----------|------|---------|-------|
| 0.7 | planner:43 | future_weight | yes | 0.4-1.0 |
| 0.8 | planner:44 | threat_weight | yes | 0.4-1.0 |
| 8.0 | planner:247 | ko_risk_critical | yes | 4-15 |
| 4.0 | planner:248 | ko_risk_high | yes | 2-8 |
| 2.0 | planner:262 | prize_race_scaling | yes | 1-4 |

---

## deck_params

Iono's Kilowattrel deck specific. Change per deck.

### Energy Attachment (ionos_rules.py)

| Value | Location | Role | Search? |
|-------|----------|------|---------|
| 100/90/80 | ionos:319-323 | enables_attack per pokemon | yes |
| 60.0 | ionos:325 | already_ready_penalty | yes |
| 40.0 | ionos:328 | progress_future | yes |
| 70-140 | ionos:334-338 | voltorb_energy_priority | yes |
| 50-100 | ionos:341-347 | bellibolt_energy_priority | yes |
| 45-100 | ionos:350-356 | kilowattrel_energy_priority | yes |
| 35.0 | ionos:370 | voltorb_damage_increase | yes |
| 400.0 | ionos:379 | voltorb_ko_line | yes |

### Bellibolt Ability Timing (ionos_rules.py)

| Value | Location | Role | Search? |
|-------|----------|------|---------|
| 280.0 | ionos:431 | enables_attack_bonus | yes |
| 250.0 | ionos:455 | charge_for_attack | yes |
| 100.0 | ionos:447 | progress_bonus | yes |
| 35.0 | ionos:441 | voltorb_scaling | yes |
| 30.0 | ionos:461 | default_bonus | yes |

### Bench / Poffin (ionos_rules.py)

| Value | Location | Role | Search? |
|-------|----------|------|---------|
| 120-45 | ionos:499-502 | poffin_bench_bonuses | yes |
| 60-35 | ionos:505-507 | poffin_missing_pokemon | yes |
| 15.0 | ionos:bench_liability | bench_low_hp_penalty_per_copy | yes |
| 20.0 | ionos:bench_liability | spread_threat_extra_penalty | yes |

---

## fixed_rules

Safety constraints. Do NOT search/modify.

| Value | Location | Role |
|-------|----------|------|
| 500.0 | engine:429 | empty_bench_loss_penalty |
| 2000.0 | engine:437 | winning_attack_boost |
| 800.0 | engine:439 | avoid_retreat_when_winning |
| 800.0 | engine:441 | avoid_end_when_winning |
| 1000.0 | engine:466 | avoid_end_with_attack |
| 1000.0 | engine:473 | avoid_retreat_with_attack |
| 50.0 | evaluator:91 | deck_out_loss |
| 30 | predictor:23 | resistance_value |

---

## Recommended Next Steps

### Priority 1: Externalize global_params for auto-tune

Top candidates for next externalization round:
1. `zero_damage_attack_penalty` (500.0) — high impact on 0-damage avoidance
2. `ko_opponent_bonus` (20.0) — KO aggression
3. `boss_can_ko` (30.0) — Boss targeting quality
4. `alt_attacker_ko_score` (800.0) — retreat-to-attacker decision
5. `win_condition_weight` (0.6) — overall strategy balance

### Priority 2: Create deck_params config

Move Iono deck-specific values to `data/deck_params_iono.json` to enable
per-deck configuration for future deck support.

### Priority 3: Tune global_params via staged pipeline

Use auto_tune_pipeline.py for 30g→50g→200g staged validation.
