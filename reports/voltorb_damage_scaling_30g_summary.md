# voltorb_damage_scaling 30g Search Results

## Setup

- Parameter: **voltorb_damage_scaling**
- Stage: **30g**
- Games: 30 per pattern
- Baseline: pattern 0 (matched game sets)

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| voltorb_damage_scaling | **0.8** |
| voltorb_ko_attack_bonus | 1000.0 (fixed) |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |
| attack_suppress_penalty | -40.0 (fixed) |

## 30g Results (sorted by anomalies/g)

| Value | Anomalies/g | Delta | vs Baseline | Safety | Decision |
|-------|-------------|-------|-------------|--------|----------|
| 1.0 | 4.83 | -0.07 | -1.4% | all 0 | hold (marginal) |
| **0.8** | **4.90** | **baseline** | - | all 0 | baseline |
| 1.2 | 4.93 | +0.03 | +0.6% | all 0 | no_promote |
| 0.6 | 5.03 | +0.13 | +2.7% | all 0 | no_promote |
| 0.4 | 5.50 | +0.60 | +12.2% worse | all 0 | no_promote |

## Safety

All candidates and baseline: safety all 0.

## Promotion Decision

**No candidates promoted to 50g.**

1.0 is formally better (-1.4%) but well within 30g noise.
All other candidates are worse than baseline.

## Trend

Lower scaling (0.4, 0.6) clearly worse. Higher scaling (1.0, 1.2) essentially tied
with baseline. The current 0.8 is near-optimal. No compelling reason to change.

## Conclusion

- voltorb_damage_scaling=0.8 remains the best value
- No further exploration needed for this parameter
- Move on to next Priority A candidate (energy_attack_enablement_bonus or evolve_first_bellibolt_bonus)

## weights.json

**Restored to 0.8. No permanent changes.**
