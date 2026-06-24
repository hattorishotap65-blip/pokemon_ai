# Area Fix Only Submission Result 001

## Submission Info

| Item | Detail |
|------|--------|
| Submission name | `area_fix_only_bonus10_candidate_001` |
| Source PR | #155 |
| File | submission.tar.gz (565 KB) |
| Date | 2026-06-24 |

## Configuration

| Setting | Value |
|---------|-------|
| `POKEMON_AI_ML_HYBRID` | 1 (ON) |
| `POKEMON_AI_ML_BONUS_RATIO` | 10.0 |
| `POKEMON_AI_AREA_FIX_MODE` | `area_fix_only` (default) |
| Attack compensation | Disabled |
| attack_plan.py | Excluded |

## Package Verification

- main.py: included
- deck.csv: included
- agent/ml_hybrid.py: included (area_fix_only default)
- configs/params/default_params.json: included
- data/: included
- cg/: included
- attack_plan.py: excluded
- experiments/artifacts/logs/docs: excluded

## Leaderboard Result

| Metric | Value |
|--------|-------|
| Public score | _pending_ |
| Previous best (#148 bonus=10) | _fill in_ |
| Difference | _pending_ |
| Status | _pending_ |

## Comparison with #148 Baseline

| Item | #148 bonus=10 | #155 area_fix_only |
|------|---------------|-------------------|
| Leaderboard score | _fill in_ | _pending_ |
| ML hybrid | ON (bonus=10) | ON (bonus=10) |
| Area fix | broken (0/1) | correct (4/5) |
| Attack compensation | N/A | Disabled |

## Decision

_To be filled after leaderboard result._

Decision rules:
- Score improved → area_fix_only becomes new primary candidate
- Score equal → area_fix_only is safe candidate, cautious update
- Score decreased → revert to #148 bonus=10 baseline

## Local Smoke (50g, pre-submission)

| Metric | Value |
|--------|-------|
| Errors | 0 |
| Timeouts | 0 |
| End+legal_attack | 0 |
| zero_damage | 0 |
| miss_KO | 1 |
| KO Capture | 99.2% (120/121) |
