# Fix Candidate Report

Generated: 2026-06-19 08:41 UTC

## Summary

| Metric | Count |
|---|---:|
| anomalies_total | 263 |
| fix_candidates | 6 |
| high_priority | 3 |
| medium_priority | 1 |
| low_priority | 2 |

## Classification Summary

| Classification | Count | Suggested Action |
|---|---:|---|
| bellibolt_attack_probably_correct | 114 | no_fix_needed |
| bellibolt_over_voltorb_high_damage | 81 | scoring_adjustment |
| voltorb_over_kilowattrel_missed | 53 | scoring_adjustment |
| voltorb_over_wattrel_missed | 13 | scoring_adjustment |
| attack_available_but_no_attack | 1 | scoring_adjustment |
| ability_without_followup_attack | 1 | scoring_adjustment |

## Fix Candidates

### F0001: Avoid attacking with Wattrel when Voltorb scaling damage is clearly superior
- priority: high
- source anomaly: best_damage_attacker_not_selected
- classification: voltorb_over_wattrel_missed
- evidence: 13 cases
- voltorb damage range: [120, 120]
- root cause hypothesis: Wattrel should not be attacking when Voltorb has significantly higher damage potential.
- suggested target files: agent/ionos_rules.py, agent/policy.py
- risk: low
- requires A/B test: True

### F0002: Prefer Voltorb scaling attack over Kilowattrel fixed 70 damage when Voltorb has high estimated damage
- priority: high
- source anomaly: best_damage_attacker_not_selected
- classification: voltorb_over_kilowattrel_missed
- evidence: 53 cases
- voltorb damage range: [120, 280]
- root cause hypothesis: Attacker selection may underweight Voltorb scaling damage compared with Kilowattrel static priority. Agent does not consider retreating to Voltorb when Voltorb has higher expected damage.
- suggested target files: agent/ionos_rules.py, agent/policy.py, data/deck_profile.json
- risk: medium
- requires A/B test: True

### F0003: Ensure attack is selected when a legal attack option exists
- priority: high
- source anomaly: attack_available_but_no_attack
- classification: attack_available_but_no_attack
- evidence: 1 cases
- root cause hypothesis: Turn ended without attacking despite a legal attack being available in the select options.
- suggested target files: agent/turn_rule_engine.py, agent/policy.py, agent/ionos_rules.py
- risk: medium
- requires A/B test: True

### F0004: Ensure Ability usage is followed by attack when possible
- priority: low
- source anomaly: ability_without_followup_attack
- classification: ability_without_followup_attack
- evidence: 1 cases
- root cause hypothesis: Root cause for ability_without_followup_attack needs investigation.
- suggested target files: tools/detect_anomalies.py
- risk: medium
- requires A/B test: True

### F0005: Consider Voltorb over Bellibolt ex when Voltorb estimated damage exceeds 230
- priority: medium
- source anomaly: best_damage_attacker_not_selected
- classification: bellibolt_over_voltorb_high_damage
- evidence: 81 cases
- voltorb damage range: [240, 400]
- root cause hypothesis: Bellibolt ex is being used as primary attacker even when Voltorb scaling damage exceeds 230. Non-ex Voltorb would be more prize-efficient.
- suggested target files: agent/ionos_rules.py, agent/policy.py, data/deck_profile.json
- risk: medium
- requires A/B test: True

## No-Fix / Detector Refinement Candidates

### F0006: Bellibolt ex attack is likely correct (Voltorb damage <= 230)
- classification: bellibolt_attack_probably_correct
- count: 114
- suggested action: no_fix_needed

## Next Recommended Action

Apply fix candidate **F0001** (voltorb_over_wattrel_missed) first.
Run `reports/latest_fix_prompt.md` in Claude Code.
