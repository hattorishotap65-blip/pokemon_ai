# Post-Adoption Smoke Check: legal_attack_score=250.0

## Current Weights

| Parameter | Value |
|-----------|-------|
| legal_attack_score | **250.0** |
| energy_attack_enablement_bonus | 200.0 |
| retreat_to_better_attacker_bonus | 1400.0 |
| attack_suppress_penalty | -40.0 |
| voltorb_ko_attack_bonus | 1000.0 |
| voltorb_damage_scaling | 0.8 |

## Smoke Test (30g)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies_total | 146 (4.87/g) |
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |

## Tests

All tests pass.

## Conclusion

- legal_attack_score=250.0 is operating correctly
- Safety all 0
- Ready for submission.tar.gz update
- submission.tar.gz is NOT yet updated in this PR
