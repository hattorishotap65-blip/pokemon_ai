# energy_to_plan_bonus 30g Search Results

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| energy_to_plan_bonus | **5.0** |
| advantage_weight | 0.4 (fixed) |
| attack_suppress_penalty | -40.0 (fixed) |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |

## 30g Results

| Value | Anomalies/g | Delta | vs Baseline | Safety | Decision |
|-------|-------------|-------|-------------|--------|----------|
| **5.0** | **4.20** | **baseline** | **-** | **all 0** | **baseline** |
| 8.0 | 4.57 | +0.37 | +8.8% worse | all 0 | no_promote |
| 4.0 | 4.87 | +0.67 | +16.0% worse | all 0 | no_promote |
| 3.0 | 5.10 | +0.90 | +21.4% worse | all 0 | no_promote |
| 6.0 | 5.10 | +0.90 | +21.4% worse | all 0 | no_promote |
| 7.0 | 5.97 | +1.77 | +42.1% worse | all 0 | no_promote |

## Safety

All candidates: safety all 0.
- attack_available_but_no_attack: 0
- end_when_attack_available: 0
- retreat_when_attack_available: 0

## Promotion Decision

**No candidates promoted to 50g.**

All candidates performed worse than baseline (5.0).
The current value of 5.0 is optimal in this range.

## Note on 30g Variance

30g results have high variance (baseline ranged from 4.20 to 8.70 across
different game sets in this session). However, relative ranking within the
same grid search run is consistent: no candidate beat the baseline.

## Conclusion

- energy_to_plan_bonus=5.0 remains the best value
- No further exploration needed for this parameter
- Move on to energy_to_plan_bonus_no_need search

## weights.json

**Restored to pre-search state. No changes.**
