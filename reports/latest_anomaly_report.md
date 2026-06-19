# Battle Log Anomaly Report

Generated: 2026-06-19 07:27 UTC

## Summary

| Metric | Count |
|---|---:|
| files | 30 |
| games | 30 |
| turns | 671 |
| actions | 5366 |
| anomalies_total | 156 |

## Severity Breakdown

| Severity | Count |
|---|---:|
| low | 156 |

## Top Issues

### best_damage_attacker_not_selected
- count: 156
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

## Representative Anomalies

### A0001
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1119.jsonl
- turn: 4
- active: 270
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_270
- why suspicious: Attacked with 270 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0002
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1119.jsonl
- turn: 5
- active: 271
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0003
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1124.jsonl
- turn: 5
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0004
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1103.jsonl
- turn: 6
- active: 271
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0005
- severity: low
- type: best_damage_attacker_not_selected
- file: game_g1119.jsonl
- turn: 6
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Suggested Next Actions

4. Run a targeted simulation to verify fixes (50+ games recommended).
