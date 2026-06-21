# energy_attack_enablement_bonus 30g Search Results

## Setup

- Parameter: **energy_attack_enablement_bonus**
- Stage: **30g**
- Games: 30 per pattern
- Baseline: pattern 0 (matched game sets)

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| energy_attack_enablement_bonus | **300.0** |
| voltorb_ko_attack_bonus | 1000.0 (fixed) |
| voltorb_damage_scaling | 0.8 (fixed) |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |
| attack_suppress_penalty | -40.0 (fixed) |

## 30g Results (sorted by anomalies/g)

| Value | Anomalies/g | Delta | vs Baseline | Safety | Decision |
|-------|-------------|-------|-------------|--------|----------|
| **200.0** | **4.73** | **-0.54** | **-10.2% better** | all 0 | **promote** |
| **400.0** | **4.73** | **-0.54** | **-10.2% better** | all 0 | **promote** |
| **300.0** | **5.27** | **baseline** | - | all 0 | baseline |
| 150.0 | 5.43 | +0.16 | +3.0% worse | all 0 | no_promote |
| 500.0 | 5.53 | +0.26 | +4.9% worse | all 0 | no_promote |

## Safety

All candidates and baseline: safety all 0.

## Promotion Decision

**200.0 and 400.0 promoted to 50g.**

Both show identical -10.2% improvement over baseline. Interesting that
both lower (200) and higher (400) values beat 300. This suggests the
exact value may not be critical, or the 30g noise is masking the real trend.

150 and 500 are worse, indicating the optimal range is between 200-400.

## Conclusion

- 200.0 and 400.0 are 50g candidates
- 150.0 and 500.0 are not viable
- 50g validation will determine which (if either) is a real improvement
- This is the first externalized weight to show 30g improvement since attack_suppress_penalty

## weights.json

**Restored to 300.0. No permanent changes.**
