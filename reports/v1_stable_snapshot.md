# v1.0-stable Snapshot

## Tag

`v1.0-stable`

## Adopted Weights

| Parameter | Value | Adopted In |
|-----------|-------|------------|
| attack_suppress_penalty | -40.0 | PR #39 |
| retreat_to_better_attacker_bonus | 1400.0 | PR #30 |
| advantage_weight | 0.4 | default |
| energy_to_plan_bonus | 5.0 | default |
| energy_to_plan_bonus_no_need | 2.0 | default |

## Validation Summary

| Parameter | 30g | 50g | 200g | Safety |
|-----------|-----|-----|------|--------|
| retreat_bonus=1400 | -12% | -18% | -8.5% | all 0 |
| attack_suppress=-40 | -11% | -11% | -9.5% | all 0 |

## Status

- Tests: 141/141
- submission.tar.gz: updated (PR #41)
- Smoke check: passed (PR #40)

## Restore

```bash
git checkout v1.0-stable
```
