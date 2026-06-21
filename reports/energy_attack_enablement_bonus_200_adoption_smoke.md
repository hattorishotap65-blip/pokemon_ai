# Post-Adoption Smoke Check: energy_attack_enablement_bonus=200.0

## Current Weights

| Parameter | Value |
|-----------|-------|
| retreat_to_better_attacker_bonus | 1400.0 |
| attack_suppress_penalty | -40.0 |
| advantage_weight | 0.4 |
| energy_to_plan_bonus | 5.0 |
| energy_to_plan_bonus_no_need | 2.0 |
| voltorb_ko_attack_bonus | 1000.0 |
| voltorb_damage_scaling | 0.8 |
| **energy_attack_enablement_bonus** | **200.0** |

## Verification

| Check | Result |
|-------|--------|
| data/weights.json energy_attack_enablement_bonus | 200.0 |
| agent/ unchanged | yes |
| deck.csv unchanged | yes |
| Tests 352/352 | pass |

## Smoke Test (30g)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies_total | 165 (5.50/g) |
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |

## Conclusion

- energy_attack_enablement_bonus=200.0 is operating correctly
- Safety all 0
- Ready for submission.tar.gz update
