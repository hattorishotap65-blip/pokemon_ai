# Attack Plan + Ionos Active Attach Submission Candidate 001

## Purpose

#163 の ablation で attack_plan ON が全指標改善したため、default ON にして submission candidate を作成。

## Configuration

| Setting | Value |
|---------|-------|
| `POKEMON_AI_ML_HYBRID` | 1 (ON) |
| `POKEMON_AI_ML_BONUS_RATIO` | 10.0 |
| `POKEMON_AI_AREA_FIX_MODE` | `area_fix_only` |
| `POKEMON_AI_IONOS_ACTIVE_ATTACH_BONUS` | 40 |
| `POKEMON_AI_IONOS_BENCH_ATTACH_PENALTY` | 20 |
| `POKEMON_AI_ATTACK_PLAN` | **1 (ON, default)** |

## #163 300g Results (why attack plan was adopted)

| Metric | A (#162 baseline) | B (+ attack plan) | Change |
|--------|------------------|-------------------|--------|
| attach_active | 52.3% | 54.1% | +1.8 pt |
| starved | 1007 | 910 | -10% |
| oversetup | 194 | 155 | -20% |
| miss_KO | 25 | 24 | -1 |
| KO capture | 96.2% | 96.7% | +0.5 pt |

## Smoke Test (100g, all defaults, no env override)

| Metric | Value |
|--------|-------|
| Games | 100 |
| Errors | 0 |
| Timeouts | 0 |
| zero_damage | 0 |
| END+legal_attack | 0 |
| miss_KO | 5 |
| KO capture | 230/235 (97.9%) |
| attach_to_active | 699/1285 (54.4%) |
| starved | 299 |
| oversetup | 52 |
| Attack when legal | 89.8% |
| ATTACK | 1295 |

## Submission Package

- **Size**: 569 KB
- **Build**: `python build_submission.py`
- **agent/attack_plan.py**: included
- **experiments/artifacts/logs/docs**: excluded

## Revert Plan

If leaderboard score drops vs #162, revert to #162 (attack_plan OFF).
Set `POKEMON_AI_ATTACK_PLAN=0` or remove attack_plan.py from build.
