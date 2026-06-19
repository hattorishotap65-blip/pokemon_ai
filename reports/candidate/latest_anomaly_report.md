# Battle Log Anomaly Report

Generated: 2026-06-19 13:18 UTC

## Summary

| Metric | Count |
|---|---:|
| files | 50 |
| games | 50 |
| turns | 1024 |
| actions | 8360 |
| anomalies_total | 301 |

## Severity Breakdown

| Severity | Count |
|---|---:|
| high | 4 |
| medium | 1 |
| low | 296 |

## Top Issues

### best_damage_attacker_not_selected
- count: 296
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

### attack_available_but_no_attack
- count: 3
- likely fix area: ionos_rules.py score_bonus attack rules, policy.py final_score integration, turn_rule_engine.py

### retreat_when_attack_available
- count: 1
- likely fix area: ionos_rules.py retreat_suppression, turn_rule_engine.py

### ability_without_followup_attack
- count: 1
- likely fix area: ionos_rules.py ability scoring, policy.py action priority

## Representative Anomalies

### A0001
- severity: high
- type: attack_available_but_no_attack
- file: game_g1918.jsonl
- turn: 3
- active: 269
- expected: attack
- actual: end
- why suspicious: A legal attack was available during this turn, but the turn ended without attacking.
- suggested fix area: turn_rule_engine.py, policy.py final_score integration, ionos_rules.py score_bonus attack rules

### A0002
- severity: high
- type: attack_available_but_no_attack
- file: game_g1929.jsonl
- turn: 3
- active: 269
- expected: attack
- actual: end
- why suspicious: A legal attack was available during this turn, but the turn ended without attacking.
- suggested fix area: turn_rule_engine.py, policy.py final_score integration, ionos_rules.py score_bonus attack rules

### A0003
- severity: high
- type: attack_available_but_no_attack
- file: game_g1947.jsonl
- turn: 3
- active: 269
- expected: attack
- actual: end
- why suspicious: A legal attack was available during this turn, but the turn ended without attacking.
- suggested fix area: turn_rule_engine.py, policy.py final_score integration, ionos_rules.py score_bonus attack rules

### A0004
- severity: high
- type: retreat_when_attack_available
- file: game_g1949.jsonl
- turn: 21
- active: 269
- expected: attack
- actual: retreat
- why suspicious: Retreat was selected while a legal Attack option existed.
- suggested fix area: ionos_rules.py retreat_suppression, turn_rule_engine.py

### A0005
- severity: medium
- type: ability_without_followup_attack
- file: game_g1929.jsonl
- turn: 3
- active: 269
- expected: ability_then_attack
- actual: ability_then_no_attack
- why suspicious: Ability was used and a legal attack was available, but the turn ended without attacking.
- suggested fix area: ionos_rules.py ability scoring, policy.py action priority

### A0006
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1931.jsonl
- turn: 3
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0007
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1902.jsonl
- turn: 4
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0008
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1930.jsonl
- turn: 4
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0009
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1932.jsonl
- turn: 4
- active: 270
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_270
- why suspicious: Attacked with 270 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0010
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1906.jsonl
- turn: 5
- active: 271
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0011
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1932.jsonl
- turn: 5
- active: 271
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0012
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1933.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0013
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1911.jsonl
- turn: 6
- active: 271
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0014
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1932.jsonl
- turn: 6
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0015
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1903.jsonl
- turn: 7
- active: 271
- expected: consider_voltorb_scaling_attack_220dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 220 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0016
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1906.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0017
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1907.jsonl
- turn: 7
- active: 271
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0018
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1916.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0019
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1926.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0020
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1931.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Suggested Next Actions

2. Check high-severity issues — attack misses and retreat-when-attack-available.
3. Review medium-severity patterns for scoring weight adjustments.
4. Run a targeted simulation to verify fixes (50+ games recommended).
