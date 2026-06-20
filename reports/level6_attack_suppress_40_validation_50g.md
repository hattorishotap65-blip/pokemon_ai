# attack_suppress_penalty=-40 Validation 50g

## 50g vs 50g Results

| Metric | Baseline (-30) | Candidate (-40) | Delta |
|--------|---------------|-----------------|-------|
| **anomalies_total** | **4.94/g** | **4.38/g** | **-0.56 (-11%)** |
| bellibolt_attack_probably_correct | 2.50 | 2.12 | -0.38 |
| bb_240_259 | 0.58 | 0.36 | -0.22 |
| kw_f0007_range_game_flow | 0.92 | 1.00 | +0.08 |
| Safety (all 4) | 0 | **0** | safe |

## 30g → 50g Consistency

| Scale | -40 vs -30 |
|-------|-----------|
| 30g | **-11%** |
| **50g** | **-11%** |

**改善が維持。** retreat_bonus=1400 と同じパターン（30g → 50g で安定）。

## Decision

**200g 検証候補として推奨。** 採用判断はまだしない。

## weights.json

**復元済み (-30.0)。**
