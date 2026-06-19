# LLM Review Packet

## Summary

- total anomalies: 156
- critical: 0
- high: 0
- medium: 0
- low: 156
- most common issue: best_damage_attacker_not_selected (156)
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

## Top 5 Anomalies

### A0001
- type: best_damage_attacker_not_selected
- severity: low
- active: 270
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_270
- why suspicious: Attacked with 270 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0002
- type: best_damage_attacker_not_selected
- severity: low
- active: 271
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0003
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0004
- type: best_damage_attacker_not_selected
- severity: low
- active: 271
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0005
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Ask

Please identify:
1. likely root cause
2. file to inspect
3. profile or weight change candidate
4. whether code change is needed
5. whether an A/B simulation is required
