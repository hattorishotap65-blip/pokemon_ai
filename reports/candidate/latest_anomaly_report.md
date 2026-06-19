# Battle Log Anomaly Report

Generated: 2026-06-19 10:56 UTC

## Summary

| Metric | Count |
|---|---:|
| files | 50 |
| games | 50 |
| turns | 1039 |
| actions | 8260 |
| anomalies_total | 232 |

## Severity Breakdown

| Severity | Count |
|---|---:|
| high | 1 |
| medium | 1 |
| low | 230 |

## Top Issues

### best_damage_attacker_not_selected
- count: 230
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

### attack_available_but_no_attack
- count: 1
- likely fix area: ionos_rules.py score_bonus attack rules, policy.py final_score integration, turn_rule_engine.py

### ability_without_followup_attack
- count: 1
- likely fix area: ionos_rules.py ability scoring, policy.py action priority

## Representative Anomalies

### A0001
- severity: high
- type: attack_available_but_no_attack
- file: game_g1518.jsonl
- turn: 3
- active: 269
- expected: attack
- actual: end
- why suspicious: A legal attack was available during this turn, but the turn ended without attacking.
- suggested fix area: turn_rule_engine.py, policy.py final_score integration, ionos_rules.py score_bonus attack rules

### A0002
- severity: medium
- type: ability_without_followup_attack
- file: game_g1518.jsonl
- turn: 3
- active: 269
- expected: ability_then_attack
- actual: ability_then_no_attack
- why suspicious: Ability was used and a legal attack was available, but the turn ended without attacking.
- suggested fix area: ionos_rules.py ability scoring, policy.py action priority

### A0003
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1501.jsonl
- turn: 4
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0004
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1506.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0005
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1509.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0006
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1512.jsonl
- turn: 5
- active: 271
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0007
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1514.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0008
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1531.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0009
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1500.jsonl
- turn: 6
- active: 271
- expected: consider_voltorb_scaling_attack_260dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 260 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0010
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1500.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0011
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1510.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0012
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1512.jsonl
- turn: 7
- active: 271
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0013
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1500.jsonl
- turn: 8
- active: 269
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0014
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1501.jsonl
- turn: 8
- active: 269
- expected: consider_voltorb_scaling_attack_220dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 220 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0015
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1523.jsonl
- turn: 8
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0016
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1506.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0017
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1509.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0018
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1512.jsonl
- turn: 9
- active: 271
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0019
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1514.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_280dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 280 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0020
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1518.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Suggested Next Actions

2. Check high-severity issues — attack misses and retreat-when-attack-available.
3. Review medium-severity patterns for scoring weight adjustments.
4. Run a targeted simulation to verify fixes (50+ games recommended).
