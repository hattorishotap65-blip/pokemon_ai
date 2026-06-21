# evolve_first_bellibolt_bonus 30g Search Results

## Setup

- Parameter: **evolve_first_bellibolt_bonus**
- Stage: **30g**
- Games: 30 per pattern
- Baseline: pattern 0 (matched game sets)

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| evolve_first_bellibolt_bonus | **220.0** |
| energy_attack_enablement_bonus | 200.0 (fixed) |
| voltorb_ko_attack_bonus | 1000.0 (fixed) |
| voltorb_damage_scaling | 0.8 (fixed) |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |
| attack_suppress_penalty | -40.0 (fixed) |

## 30g Results (sorted by anomalies/g)

| Value | Anomalies/g | Delta | vs Baseline | Safety | Decision |
|-------|-------------|-------|-------------|--------|----------|
| **330.0** | **4.00** | **-0.97** | **-19.5% better** | all 0 | **promote** |
| 110.0 | 4.57 | -0.40 | -8.1% | all 0 | hold (marginal) |
| 275.0 | 4.57 | -0.40 | -8.1% | all 0 | hold (marginal) |
| **220.0** | **4.97** | **baseline** | - | all 0 | baseline |
| 165.0 | 5.00 | +0.03 | +0.6% | all 0 | no_promote |

## Safety

All candidates and baseline: safety all 0.

## Promotion Decision

**330.0 promoted to 50g.** 110.0 and 275.0 held (marginal at -8%).

## Trend

Higher evolve priority (275, 330) tends to improve anomaly count.
330.0 is the clear best at -20%. This suggests prioritizing early
Bellibolt evolution more strongly is beneficial.

## Conclusion

- evolve_first_bellibolt_bonus=330.0 is the 50g candidate
- 50g validation will confirm if the improvement holds
- This follows the pattern seen with other weights: stronger bonuses help

## weights.json

**Restored to 220.0. No permanent changes.**
