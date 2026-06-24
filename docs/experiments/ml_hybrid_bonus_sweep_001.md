# ML Hybrid Bonus Sweep 001

## Purpose

Compare ML hybrid bonus ratios around the current best (bonus=10) to find the optimal submission candidate.

## Background

| PR | Description |
|----|-------------|
| #134 | Baseline clean submission candidate |
| #148 | ML hybrid bonus=10 — improved leaderboard over #134 |
| #149 | Recorded #148 result |

## Why Bonus Sweep

- #148 bonus=10 improved leaderboard score vs baseline
- Nearby ratios (8, 12, 15) may perform better
- bonus=20 showed large overhead in #147/#146 — excluded from primary comparison

## Compared Ratios

| Ratio | Hypothesis |
|-------|------------|
| 8.0 | Conservative — fewer decision changes, smaller improvement ceiling |
| 10.0 | Current best — already improved leaderboard |
| 12.0 | Most promising alternative — slightly more aggressive, likely still safe |
| 15.0 | Aggressive — watch for overhead and action distribution skew |

## Commands

```bash
# Full sweep (runs 4x100g self-play + aggregation)
bash scripts/run_bonus_sweep.sh

# Individual runs
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=8.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 260000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus8_100g.jsonl

POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=10.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 261000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus10_100g.jsonl

POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=12.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 262000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus12_100g.jsonl

POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=15.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 263000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus15_100g.jsonl

# Aggregate
python experiments/compare_ml_hybrid_bonus.py \
  --inputs \
    bonus8=artifacts/ml_hybrid_bonus8_100g.jsonl \
    bonus10=artifacts/ml_hybrid_bonus10_100g.jsonl \
    bonus12=artifacts/ml_hybrid_bonus12_100g.jsonl \
    bonus15=artifacts/ml_hybrid_bonus15_100g.jsonl \
  --summary artifacts/ml_hybrid_bonus_sweep_summary.json
```

## Self-Play Results

_To be filled after running the sweep._

| Bonus | Games | Wins | Losses | Win Rate | Errors | Timeouts |
|-------|-------|------|--------|----------|--------|----------|
| 8.0 | — | — | — | — | — | — |
| 10.0 | — | — | — | — | — | — |
| 12.0 | — | — | — | — | — | — |
| 15.0 | — | — | — | — | — | — |

## Safety Metrics

| Bonus | End+legal_attack | zero_damage | miss_KO | gate_blocked |
|-------|------------------|-------------|---------|--------------|
| 8.0 | — | — | — | — |
| 10.0 | — | — | — | — |
| 12.0 | — | — | — | — |
| 15.0 | — | — | — | — |

## Runtime Overhead

| Bonus | avg ms/game | avg decision time | notes |
|-------|-------------|-------------------|-------|
| 8.0 | — | — | — |
| 10.0 | — | — | ~4725ms (#148) |
| 12.0 | — | — | — |
| 15.0 | — | — | — |

## Action Type Distribution

| Bonus | ATTACK | ATTACH | END | RETREAT | Decisions |
|-------|--------|--------|-----|---------|-----------|
| 8.0 | — | — | — | — | — |
| 10.0 | — | — | — | — | — |
| 12.0 | — | — | — | — | — |
| 15.0 | — | — | — | — | — |

## Findings

_To be filled after analysis._

## Recommendation

_To be filled after analysis._

### Selection Criteria

Priority 1 (must pass):
- errors = 0
- timeouts = 0
- End+legal_attack = 0
- zero_damage = 0
- miss_KO not worse than bonus=10

Priority 2 (prefer):
- avg ms/game <= bonus=10
- action type distribution not skewed
- changed decision rate not excessive

Priority 3 (leaderboard):
- Score higher than #148 bonus=10 → adopt
- Score similar → pick safer/faster option
- Score lower → keep bonus=10

## Next Steps

- Run sweep and fill tables
- If a ratio beats bonus=10: prepare submission candidate PR
- If bonus=10 remains best: close experiment, keep #148 as primary
- bonus=20 deferred due to overhead concerns (#147/#146)
