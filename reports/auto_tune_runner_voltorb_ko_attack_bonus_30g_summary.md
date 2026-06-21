# voltorb_ko_attack_bonus 30g Search Results

## Setup

- Parameter: **voltorb_ko_attack_bonus**
- Stage: **30g**
- Games: 30 per pattern
- Baseline: pattern 0 (matched game sets)
- Tool: auto_tune_runner.py + weight_search.py

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| voltorb_ko_attack_bonus | **1000.0** |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |
| attack_suppress_penalty | -40.0 (fixed) |
| advantage_weight | 0.4 (fixed) |
| energy_to_plan_bonus | 5.0 (fixed) |
| energy_to_plan_bonus_no_need | 2.0 (fixed) |

## 30g Results (sorted by anomalies/g)

| Value | Anomalies/g | Delta | vs Baseline | Safety | Decision |
|-------|-------------|-------|-------------|--------|----------|
| **1250.0** | **4.53** | **-5.24** | **-53.6% better** | all 0 | **promote** |
| 1500.0 | 5.13 | -4.64 | -47.5% better | all 0 | promote |
| 500.0 | 8.23 | -1.54 | -15.8% better | all 0 | promote |
| 750.0 | 9.03 | -0.74 | -7.6% better | all 0 | promote |
| **1000.0** | **9.77** | **baseline** | - | all 0 | baseline |

## Safety

All candidates and baseline: safety all 0.

## Promotion Decision

All 4 candidates beat baseline, but with strong pattern:
- **Higher values (1250, 1500) dramatically better than lower values (500, 750)**
- This suggests the KO bonus should be even stronger than 1000

**Recommended 50g candidates: 1250.0 and 1500.0**

500.0 and 750.0 formally promoted but improvement is small and direction is opposite
to the clear trend (higher = better). Held for now.

## Note on 30g Variance

Baseline measured at 9.77/g which is higher than typical 4.5-5.0 range.
However, all patterns ran in the same grid with matched game set ranges,
so relative comparison is valid.

## Conclusion

- voltorb_ko_attack_bonus=1250.0 is the clear 50g candidate
- 1500.0 is second candidate
- Higher KO bonus = better performance (stronger KO aggression pays off)
- 50g validation needed to confirm

## weights.json

**Restored to 1000.0. No permanent changes.**
