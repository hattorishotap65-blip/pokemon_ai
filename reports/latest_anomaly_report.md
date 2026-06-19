# Battle Log Anomaly Report

Generated: 2026-06-19 08:20 UTC

## Summary

| Metric | Count |
|---|---:|
| files | 30 |
| games | 30 |
| turns | 621 |
| actions | 4919 |
| anomalies_total | 158 |

## Severity Breakdown

| Severity | Count |
|---|---:|
| low | 158 |

## Top Issues

### best_damage_attacker_not_selected
- count: 158
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

## Representative Anomalies

### A0001
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1222.jsonl
- turn: 3
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0002
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1227.jsonl
- turn: 3
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0003
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1202.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0004
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1205.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0005
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1207.jsonl
- turn: 6
- active: 271
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0006
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1209.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0007
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1213.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_220dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 220 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0008
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1222.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0009
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1227.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0010
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1229.jsonl
- turn: 7
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0011
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1203.jsonl
- turn: 8
- active: 271
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0012
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1215.jsonl
- turn: 8
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0013
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1200.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0014
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1201.jsonl
- turn: 9
- active: 271
- expected: consider_voltorb_scaling_attack_240dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 240 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0015
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1202.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0016
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1204.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0017
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1205.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_260dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 260 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0018
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1206.jsonl
- turn: 9
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0019
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1203.jsonl
- turn: 10
- active: 271
- expected: consider_voltorb_scaling_attack_220dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 220 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0020
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1225.jsonl
- turn: 10
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Suggested Next Actions

4. Run a targeted simulation to verify fixes (50+ games recommended).
