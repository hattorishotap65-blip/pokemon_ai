# Post-Adoption Smoke Check: retreat_to_better_attacker_bonus=1400

## Verification

| Check | Result |
|-------|--------|
| data/weights.json = 1400.0 | **OK** |
| submission.tar.gz contains 1400.0 | **OK** |
| deck.csv unchanged | **OK** |
| agent/ logic unchanged | **OK** |

## Smoke Test (30g)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies_total | 138 (4.60/g) |
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |

## Conclusion

- retreat_to_better_attacker_bonus=1400 が正しく採用されている
- submission.tar.gz にも反映済み
- 30g smoke test で safety all 0
- anomalies_total 4.60/g は 200g 検証時の 4.97/g と同等以下
- **提出物として問題なし**
