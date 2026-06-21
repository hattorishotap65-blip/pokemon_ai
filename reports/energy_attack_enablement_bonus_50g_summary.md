# energy_attack_enablement_bonus 50g Validation

## Setup

| | Value | Games |
|-|-------|-------|
| **Baseline** | energy_attack_enablement_bonus=**300.0** | 50 |
| **Candidate 1** | energy_attack_enablement_bonus=**200.0** | 50 |
| **Candidate 2** | energy_attack_enablement_bonus=**400.0** | 50 |
| Matched game sets | **Yes** (pattern 0 = baseline) | |

All other weights fixed at stable baseline.

## 30g Context

| Value | 30g /game | 30g vs baseline |
|-------|-----------|-----------------|
| 300.0 | 5.27 | baseline |
| 200.0 | 4.73 | -10.2% |
| 400.0 | 4.73 | -10.2% |

## 50g Results

| Value | /game | Delta | vs Baseline | Safety | Decision |
|-------|-------|-------|-------------|--------|----------|
| **200.0** | **4.30** | **-0.76** | **-15.0% better** | all 0 | **promote** |
| 400.0 | 4.90 | -0.16 | -3.2% | all 0 | hold (marginal) |
| **300.0** | **5.06** | **baseline** | - | all 0 | baseline |

## Consistency Check

| Stage | 200.0 vs baseline | 400.0 vs baseline |
|-------|--------------------|--------------------|
| 30g | **-10.2% better** | **-10.2% better** |
| **50g** | **-15.0% better** | -3.2% (marginal) |

**200.0 improvement is consistent and strengthening.** 400.0 faded at 50g.

## Safety

All patterns: safety all 0.

## Promotion Decision

**200.0 promoted to 200g.** 400.0 held (marginal at 50g).

## Conclusion

- energy_attack_enablement_bonus=200.0 is the clear 200g candidate
- Improvement consistent: 30g=-10%, 50g=-15%
- This follows the same pattern as attack_suppress_penalty (improvement strengthened at 50g)
- 200g confirmation needed before adoption

## weights.json

**Restored to 300.0. No permanent changes.**
