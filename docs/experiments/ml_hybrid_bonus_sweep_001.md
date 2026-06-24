# ML Hybrid Bonus Sweep 001

## Purpose

Compare ML hybrid bonus ratios around the current best (bonus=10) to find the optimal submission candidate.

## Background

| PR | Description |
|----|-------------|
| #134 | Baseline clean submission candidate |
| #148 | ML hybrid bonus=10 — improved leaderboard over #134 |
| #149 | Recorded #148 result |
| #150 | Sweep infrastructure and aggregation scripts |

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

| Bonus | Games | Errors | Timeouts | Decisions | Candidates | Avg selections |
|-------|-------|--------|----------|-----------|------------|----------------|
| 8.0 | 100 | 0 | 0 | 21107 | 97291 | 4.61 |
| 10.0 | 100 | 0 | 0 | 18953 | 86179 | 4.55 |
| 12.0 | 100 | 0 | 0 | 20489 | 93498 | 4.56 |
| 15.0 | 100 | 0 | 0 | 20323 | 92446 | 4.55 |

Note: Win/Loss not available — self-play result detection returned `unknown` for all games (symmetric self-play with log-based detection). Safety metrics and action distribution are the primary comparison axes.

## Safety Metrics

| Bonus | End+legal_attack | zero_damage | miss_KO |
|-------|------------------|-------------|---------|
| 8.0 | 0 | 0 | 8 |
| **10.0** | **0** | **0** | **2** |
| 12.0 | 0 | 0 | 11 |
| 15.0 | 0 | 0 | 11 |

**Key finding**: bonus=10 has the lowest miss_KO (2), significantly better than bonus=12 (11) and bonus=15 (11). bonus=8 is intermediate at 8.

## Runtime Overhead

_Note: avg ms/game is reported by `run_matches_real.py` stdout, not in the JSONL. Not available for this run._

| Bonus | avg ms/game | notes |
|-------|-------------|-------|
| 8.0 | N/A | — |
| 10.0 | N/A | ~4725ms in #148 |
| 12.0 | N/A | — |
| 15.0 | N/A | — |

## Action Type Distribution (selected actions)

| Bonus | ATTACK | ATTACH | END | RETREAT | ABILITY | PLAY | EVOLVE |
|-------|--------|--------|-----|---------|---------|------|--------|
| 8.0 | 1270 | 1304 | 1043 | 398 | 3427 | 2586 | 681 |
| 10.0 | 1180 | 1209 | 978 | 324 | 3019 | 2395 | 609 |
| 12.0 | 1245 | 1260 | 1129 | 366 | 3293 | 2504 | 670 |
| 15.0 | 1197 | 1264 | 980 | 331 | 3350 | 2521 | 665 |

### Normalized per 100 decisions

| Bonus | ATTACK% | ATTACH% | END% | RETREAT% |
|-------|---------|---------|------|----------|
| 8.0 | 6.0% | 6.2% | 4.9% | 1.9% |
| 10.0 | 6.2% | 6.4% | 5.2% | 1.7% |
| 12.0 | 6.1% | 6.1% | 5.5% | 1.8% |
| 15.0 | 5.9% | 6.2% | 4.8% | 1.6% |

Action distribution is stable across all ratios — no extreme skew observed.

## KO capture analysis

| Bonus | can_ko candidates | selected can_ko | capture rate |
|-------|-------------------|-----------------|--------------|
| 8.0 | 203 | 195 | 96.1% |
| 10.0 | 213 | 211 | 99.1% |
| 12.0 | 221 | 210 | 95.0% |
| 15.0 | 230 | 219 | 95.2% |

bonus=10 has the highest KO capture rate at 99.1%.

## Findings

1. **All ratios pass safety baseline**: errors=0, timeouts=0, End+legal_attack=0, zero_damage=0 for all four ratios.

2. **bonus=10 is clearly safest on miss_KO**: miss_KO=2 vs 8/11/11 for others. This means bonus=10 is the best at not missing available KO opportunities.

3. **bonus=10 has highest KO capture rate**: 99.1% vs 95-96% for others.

4. **Action distributions are similar**: No ratio shows extreme skew. All have similar ATTACK/ATTACH/END/RETREAT proportions.

5. **bonus=10 has fewer total decisions** (18953 vs 20-21k), suggesting games may resolve slightly faster.

6. **bonus=12 and bonus=15 increase miss_KO significantly** (11 each), which contradicts the hypothesis that higher bonus would be more aggressive in a beneficial way.

7. **bonus=8 is in between** (miss_KO=8), neither the safest nor the most aggressive.

## Recommendation

**Maintain bonus=10 (#148) as the primary submission candidate.**

Rationale:
- bonus=10 has the best miss_KO score (2) — significantly better than all other ratios tested
- bonus=10 has the highest KO capture rate (99.1%)
- bonus=10 already improved leaderboard vs baseline (#134)
- bonus=12 and bonus=15 worsen miss_KO by 5.5x, suggesting higher bonus ratios distort scoring priorities
- bonus=8 is also worse than bonus=10 on miss_KO
- Action distribution is stable across all ratios, so no behavioral advantage from changing

### Decision

- **Do not change bonus ratio from 10.0**
- #148 bonus=10 remains the current best submission candidate
- No additional submission candidate PR needed for bonus ratio adjustment
- Consider other improvement axes (safety gates, card knowledge, opponent modeling) instead of further bonus tuning

## Next Steps

- Close this experiment — bonus=10 is confirmed as optimal in the 8-15 range
- Focus on other improvement areas rather than further bonus ratio sweeps
- If leaderboard score plateaus, consider entirely different approaches rather than fine-tuning bonus
