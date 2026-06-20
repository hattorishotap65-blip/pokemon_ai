# attack_suppress_penalty=-40 Validation 200g

## 200g vs 200g Results

| Metric | Baseline (-30) | Candidate (-40) | Delta |
|--------|---------------|-----------------|-------|
| **anomalies_total** | **4.97/g** | **4.50/g** | **-0.47 (-9.5%)** |
| bellibolt_attack_probably_correct | 2.54 | 2.19 | -0.35 |
| kw_f0007_range_game_flow | 0.92 | 0.83 | -0.09 |
| bb_f0007_range_no_retreat | 0.50 | 0.55 | +0.05 |
| Safety (all 4) | 0 | **0** | safe |

## Consistency Across All Scales

| Scale | -40 vs -30 |
|-------|-----------|
| 30g | **-11%** |
| 50g | **-11%** |
| **200g** | **-9.5%** |

**30g → 50g → 200g で一貫して改善。** retreat_bonus=1400 と同じ成功パターン。

## Decision

**採用候補として推奨。**

## weights.json

**復元済み (-30.0)。**
