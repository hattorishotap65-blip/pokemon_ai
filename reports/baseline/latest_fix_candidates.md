# Fix Candidate Report

Generated: 2026-06-19 10:52 UTC

## Summary

| Metric | Count |
|---|---:|
| anomalies_total | 257 |
| fix_candidates | 4 |
| high_priority | 2 |
| medium_priority | 1 |
| low_priority | 1 |

## Classification Summary

| Classification | Count | Suggested Action |
|---|---:|---|
| bellibolt_attack_probably_correct | 108 | no_fix_needed |
| bellibolt_over_voltorb_high_damage | 89 | scoring_adjustment |
| voltorb_over_kilowattrel_missed | 55 | scoring_adjustment |
| voltorb_over_wattrel_missed | 5 | scoring_adjustment |

## Fix Candidates

### F0001: Avoid attacking with Wattrel when Voltorb scaling damage is clearly superior
- priority: high
- source anomaly: best_damage_attacker_not_selected
- classification: voltorb_over_wattrel_missed
- evidence: 5 cases
- voltorb damage range: [120, 120]
- root cause hypothesis: Wattrel should not be attacking when Voltorb has significantly higher damage potential.
- suggested target files: agent/ionos_rules.py, agent/policy.py
- risk: low
- requires A/B test: True

### F0002: Prefer Voltorb scaling attack over Kilowattrel fixed 70 damage when Voltorb has high estimated damage
- priority: high
- source anomaly: best_damage_attacker_not_selected
- classification: voltorb_over_kilowattrel_missed
- evidence: 55 cases
- voltorb damage range: [140, 360]
- root cause hypothesis: Attacker selection may underweight Voltorb scaling damage compared with Kilowattrel static priority. Agent does not consider retreating to Voltorb when Voltorb has higher expected damage.
- suggested target files: agent/ionos_rules.py, agent/policy.py, data/deck_profile.json
- risk: medium
- requires A/B test: True

### F0003: Consider Voltorb over Bellibolt ex when Voltorb estimated damage exceeds 230
- priority: medium
- source anomaly: best_damage_attacker_not_selected
- classification: bellibolt_over_voltorb_high_damage
- evidence: 89 cases
- voltorb damage range: [240, 440]
- root cause hypothesis: Bellibolt ex is being used as primary attacker even when Voltorb scaling damage exceeds 230. Non-ex Voltorb would be more prize-efficient.
- suggested target files: agent/ionos_rules.py, agent/policy.py, data/deck_profile.json
- risk: medium
- requires A/B test: True

## No-Fix / Detector Refinement Candidates

### F0004: Bellibolt ex attack is likely correct (Voltorb damage <= 230)
- classification: bellibolt_attack_probably_correct
- count: 108
- suggested action: no_fix_needed

## Next Recommended Action

Apply fix candidate **F0001** (voltorb_over_wattrel_missed) first.
Run `reports/latest_fix_prompt.md` in Claude Code.
