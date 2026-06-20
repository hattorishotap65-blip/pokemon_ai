# energy_to_plan_bonus_no_need=1.0 — 50g Validation

## Setup

| | Value | Games |
|-|-------|-------|
| **Baseline** | energy_to_plan_bonus_no_need=**2.0** | 50 |
| **Candidate** | energy_to_plan_bonus_no_need=**1.0** | 50 |
| Matched game sets | **Yes** | |

All other weights fixed:
- advantage_weight=0.4
- energy_to_plan_bonus=5.0
- attack_suppress_penalty=-40.0
- retreat_to_better_attacker_bonus=1400.0

## 50g Results

| Config | Anomalies/g | Safety |
|--------|-------------|--------|
| **Baseline (2.0)** | **4.62** | all 0 |
| Candidate (1.0) | 4.66 | all 0 |

| Metric | Value |
|--------|-------|
| Delta | +0.04 |
| vs Baseline | +0.87% worse |
| Safety | all 0 |
| Decision | **no_promote** |

## Consistency Check

| Stage | Result |
|-------|--------|
| 30g | 1.0 best in grid (4.97/g) but baseline was separate game set (8.37/g) |
| **50g** | **1.0=4.66 vs 2.0=4.62 (matched). No improvement.** |

The 30g result was misleading due to different game sets.
At 50g with matched conditions, candidate 1.0 is essentially identical to baseline 2.0 (+0.87%).

## Promotion Decision

**Not promoted to 200g.**

The candidate showed no improvement over baseline at 50g.
energy_to_plan_bonus_no_need=2.0 remains the best value.

## Conclusion

- energy_to_plan_bonus_no_need=1.0 does not improve over 2.0
- No further exploration needed for this parameter
- All 3 tunable weights (advantage_weight, energy_to_plan_bonus, energy_to_plan_bonus_no_need) confirmed at current stable values

## weights.json

**Restored to pre-search state. No changes.**
