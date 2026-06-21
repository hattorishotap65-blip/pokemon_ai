# energy_attack_enablement_bonus Adoption

## Decision

**ADOPT energy_attack_enablement_bonus=200.0** (was 300.0)

## Validation Summary

| Stage | 200.0 vs baseline 300.0 | Safety |
|-------|-------------------------|--------|
| 30g (PR #60) | -10.2% | all 0 |
| 50g (PR #61) | -15.0% | all 0 |
| 200g (PR #62) | **-21.0%** | all 0 |

Improvement consistent and strengthening across all scales.

## Change

```diff
- "energy_attack_enablement_bonus": 300.0,
+ "energy_attack_enablement_bonus": 200.0,
```

## Current Stable Weights

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

## Next Step

- Smoke check
- submission.tar.gz update (separate PR)
