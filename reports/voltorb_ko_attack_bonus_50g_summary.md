# voltorb_ko_attack_bonus 50g Validation

## Setup

| | Value | Games |
|-|-------|-------|
| **Baseline** | voltorb_ko_attack_bonus=**1000.0** | 50 |
| **Candidate 1** | voltorb_ko_attack_bonus=**1250.0** | 50 |
| **Candidate 2** | voltorb_ko_attack_bonus=**1500.0** | 50 |
| Matched game sets | **Yes** (pattern 0 = baseline) | |

All other weights fixed at stable baseline.

## 30g Context

| Value | 30g /game | 30g vs baseline |
|-------|-----------|-----------------|
| 1000.0 | 9.77 | baseline |
| 1250.0 | 4.53 | -54% |
| 1500.0 | 5.13 | -48% |

## 50g Results

| Value | /game | Delta | vs Baseline | Safety | Decision |
|-------|-------|-------|-------------|--------|----------|
| **1000.0** | **4.06** | **baseline** | - | all 0 | baseline |
| 1500.0 | 4.76 | +0.70 | +17% worse | all 0 | no_promote |
| 1250.0 | 5.92 | +1.86 | +46% worse | all 0 | no_promote |

## Consistency Check

| Stage | 1250.0 vs baseline | 1500.0 vs baseline |
|-------|--------------------|--------------------|
| 30g | **-54% better** | **-48% better** |
| **50g** | **+46% worse** | **+17% worse** |

**30g improvement not confirmed at 50g.** Both candidates are worse than baseline at 50g.

## Promotion Decision

**No candidates promoted to 200g.**

## Safety

All patterns: safety all 0.

## Conclusion

- voltorb_ko_attack_bonus=1000.0 remains the best value
- 30g results were misleading due to high variance (baseline was 9.77/g at 30g vs 4.06/g at 50g)
- No further exploration needed for this parameter at this time
- Consider exploring Priority A2 (voltorb_damage_scaling) or other candidates next

## weights.json

**Restored to 1000.0. No permanent changes.**
