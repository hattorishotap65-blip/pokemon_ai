# Post-Adoption Smoke Check: attack_suppress_penalty=-40.0

## Current Weights

| Parameter | Value |
|-----------|-------|
| attack_suppress_penalty | **-40.0** |
| retreat_to_better_attacker_bonus | **1400.0** |

## Verification

| Check | Result |
|-------|--------|
| data/weights.json attack_suppress_penalty | -40.0 ✓ |
| data/weights.json retreat_to_better_attacker_bonus | 1400.0 ✓ |
| agent/ unchanged | ✓ |
| deck.csv unchanged | ✓ |
| Tests 141/141 | ✓ |

## Smoke Test (30g)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies_total | 173 (5.77/g) |
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |

anomalies 5.77/g は 30g の分散範囲内（200g 検証では 4.50/g）。

## Conclusion

- attack_suppress_penalty=-40.0 が正しく反映されている
- Safety all 0
- submission.tar.gz 更新へ進めてよい
