# advantage_weight 30g Search Results

## Stable Baseline

| Parameter | Value |
|-----------|-------|
| advantage_weight | **0.4** |
| attack_suppress_penalty | -40.0 (fixed) |
| retreat_to_better_attacker_bonus | 1400.0 (fixed) |

## 30g Results

| Value | Anomalies/g | Delta | vs Baseline | Safety | Decision |
|-------|-------------|-------|-------------|--------|----------|
| **0.4** | **4.53** | **baseline** | **-** | **all 0** | **baseline** |
| 0.2 | 4.73 | +0.20 | +4.4% | all 0 | no_promote |
| 0.3 | 4.67 | +0.14 | +3.1% | all 0 | no_promote |
| 0.5 | 4.97 | +0.44 | +9.7% | all 0 | no_promote |
| 0.6 | 5.30 | +0.77 | +17.0% | all 0 | no_promote |

## Safety

All candidates: safety all 0.
- attack_available_but_no_attack: 0
- end_when_attack_available: 0
- retreat_when_attack_available: 0

## Promotion Decision

**No candidates promoted to 50g.**

All candidates performed worse than baseline (0.4).
The current value of 0.4 is optimal in this range.

## Trend

Lower advantage_weight (0.2, 0.3) is slightly better than higher (0.5, 0.6),
but none beat the current 0.4. The advantage_weight parameter appears well-tuned.

## Conclusion

- advantage_weight=0.4 remains the best value
- No further exploration needed for this parameter
- Move on to energy_to_plan_bonus search

## weights.json

**Restored to pre-search state. No changes.**
