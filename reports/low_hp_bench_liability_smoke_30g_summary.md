# Smoke Check: Low HP Bench Liability Rules (PR #83)

## Purpose

Verify that PR #83's low HP bench liability, spread threat detection,
and Poffin diversity rules do not cause regressions in normal play.

## Smoke Test (30g)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies_total | 174 (5.80/g) |
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |

## Tests

All tests pass (82 turn_rule + 17 bench_liability + others).

## Preserved Rules

- #80 empty_bench_loss_prevention: maintained
- #82 winning_attack_guard: maintained

## Conclusion

- Safety all 0: no attack suppression regressions
- Normal attack and bench behavior preserved
- Ready for submission.tar.gz update
