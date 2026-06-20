# energy_to_plan_bonus_no_need 30g Search Results

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| energy_to_plan_bonus_no_need | **2.0** |
| advantage_weight | 0.4 (fixed) |
| energy_to_plan_bonus | 5.0 (fixed) |
| attack_suppress_penalty | -40.0 (fixed) |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |

## 30g Results

| Value | Anomalies/g | Safety | Grid Rank |
|-------|-------------|--------|-----------|
| 1.0 | 4.97 | all 0 | 1st (best) |
| 3.0 | 6.10 | all 0 | 2nd |
| 4.0 | 6.80 | all 0 | 3rd |
| **2.0** (baseline) | **8.37** | **all 0** | **(separate game set)** |

## Safety

All candidates: safety all 0.
- attack_available_but_no_attack: 0
- end_when_attack_available: 0
- retreat_when_attack_available: 0

## Important Note on 30g Variance

The baseline (2.0) was measured from a **separate game set** and shows 8.37/g,
which is much higher than the typical 4.5-5.0/g range seen in other searches.
This is 30g variance, not a real difference in agent quality.

The grid search candidates (1.0, 3.0, 4.0) ran on a different game set
and show 4.97-6.80/g. **Direct comparison between baseline and candidates
is unreliable due to different game sets.**

However, the **relative ranking within the grid search** (1.0 < 3.0 < 4.0)
is meaningful because they ran on the same game set range.

## Promotion Decision

Formally, all 3 candidates show lower anomalies than the separately-measured
baseline. However, due to high 30g variance and different game sets:

- **energy_to_plan_bonus_no_need=1.0**: Best within grid. Worth 50g validation.
- energy_to_plan_bonus_no_need=3.0: 2nd best but worse than baseline in Run 002 (5.83/g).
- energy_to_plan_bonus_no_need=4.0: 3rd. Not convincing.

**Recommended 50g candidate: 1.0 only.**

The 50g validation will use the same game set for baseline and candidate,
eliminating the game-set variance issue.

## Conclusion

- energy_to_plan_bonus_no_need=1.0 is the only candidate worth 50g validation
- 3.0 and 4.0 are not convincing at 30g
- 50g will provide reliable comparison with matched game sets

## weights.json

**Restored to pre-search state. No changes.**
