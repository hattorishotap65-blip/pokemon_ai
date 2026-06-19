# LLM Review Packet

## Summary

- total anomalies: 158
- critical: 0
- high: 0
- medium: 0
- low: 158
- most common issue: best_damage_attacker_not_selected (158)
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

## Top 10 Anomalies

### A0001
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0002
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0003
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0004
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0005
- type: best_damage_attacker_not_selected
- severity: low
- active: 271
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0006
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0007
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_220dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 220 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0008
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0009
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_120dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 120 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0010
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_180dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 180 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Ask

Please identify:
1. likely root cause
2. file to inspect
3. profile or weight change candidate
4. whether code change is needed
5. whether an A/B simulation is required
