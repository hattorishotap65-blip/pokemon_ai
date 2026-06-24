# Ionos Active Attach Submission Candidate 001

## Purpose

#161 D variant を default 化し、leaderboard 確認用の submission candidate を作成。

## Configuration

| Setting | Value |
|---------|-------|
| `POKEMON_AI_ML_HYBRID` | 1 (ON) |
| `POKEMON_AI_ML_BONUS_RATIO` | 10.0 |
| `POKEMON_AI_AREA_FIX_MODE` | `area_fix_only` |
| `POKEMON_AI_IONOS_ACTIVE_ATTACH_BONUS` | **40** (default) |
| `POKEMON_AI_IONOS_BENCH_ATTACH_PENALTY` | **20** (default) |
| attack_plan.py | excluded |

## Why D Variant

#161 300g ablation result:

| Metric | Baseline (0/0) | D (+40/-20) | Change |
|--------|---------------|-------------|--------|
| attach_to_active | 49.5% | 52.8% | +3.3 pt |
| active_energy_starved | 1122 | 990 | -12% |
| bench_oversetup | 210 | 183 | -13% |
| miss_KO | 33 | 26 | -21% |
| KO capture | 95.5% | 96.2% | +0.7 pt |

D improves all target metrics without safety regressions.

## Smoke Test (100g, D default, no env override)

| Metric | Value |
|--------|-------|
| Games | 100 |
| Errors | 0 |
| Timeouts | 0 |
| zero_damage | 0 |
| miss_KO | 7 |
| KO capture | 207/214 (96.7%) |
| attach_to_active | 691/1319 (52.4%) |
| active_energy_starved | 340 |
| bench_oversetup | 31 |
| ATTACK | 1203 |
| ATTACH | 1319 |
| END | 969 |
| Decisions | 20475 |

## Submission Package

- **Size**: 566 KB
- **Build**: `python build_submission.py`

### Included
- main.py, deck.csv, agent/ (ionos_rules.py with D defaults), configs/, data/, cg/

### Excluded
- attack_plan.py, experiments/, artifacts/, logs/, docs/, .git/

## Decision

Ready for leaderboard test. If score drops vs #155, revert to #155 area_fix_only.
