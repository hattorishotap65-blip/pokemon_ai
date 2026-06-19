# LLM Review Packet

## Summary

- total anomalies: 232
- critical: 0
- high: 1
- medium: 1
- low: 230
- most common issue: best_damage_attacker_not_selected (230)
- likely fix area: data/deck_profile.json attacker_selection_policy, ionos_rules.py attacker selection

## Top 10 Anomalies

### A0001
- type: attack_available_but_no_attack
- severity: high
- active: 269
- expected: attack
- actual: end
- why suspicious: A legal attack was available during this turn, but the turn ended without attacking.
- suggested fix area: turn_rule_engine.py, policy.py final_score integration, ionos_rules.py score_bonus attack rules

### A0002
- type: ability_without_followup_attack
- severity: medium
- active: 269
- expected: ability_then_attack
- actual: ability_then_no_attack
- why suspicious: Ability was used and a legal attack was available, but the turn ended without attacking.
- suggested fix area: ionos_rules.py ability scoring, policy.py action priority

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
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0005
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0006
- type: best_damage_attacker_not_selected
- severity: low
- active: 271
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0007
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_200dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 200 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0008
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_140dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 140 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0009
- type: best_damage_attacker_not_selected
- severity: low
- active: 271
- expected: consider_voltorb_scaling_attack_260dmg
- actual: attacked_with_271
- why suspicious: Attacked with 271 instead of Voltorb. Voltorb estimated damage was 260 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

### A0010
- type: best_damage_attacker_not_selected
- severity: low
- active: 269
- expected: consider_voltorb_scaling_attack_160dmg
- actual: attacked_with_269
- why suspicious: Attacked with 269 instead of Voltorb. Voltorb estimated damage was 160 (high scaling), which may have been a better prize-race option.
- suggested fix area: ionos_rules.py attacker selection, data/deck_profile.json attacker_selection_policy

## Ask

Please identify:
1. likely root cause
2. file to inspect
3. profile or weight change candidate
4. whether code change is needed
5. whether an A/B simulation is required
