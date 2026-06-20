# attack_suppress_penalty Re-evaluation (30g, with retreat_bonus=1400)

## Context

Level 6 Run 002 (pre-retreat_bonus=1400) では -20/-40 ともに baseline より悪化。
今回は retreat_bonus=1400 採用後に再評価。

## 30g Results

| Value | Anomalies | /game | vs baseline (-30) | Safety |
|-------|-----------|-------|-------------------|--------|
| -20.0 | 155 | 5.17 | +4% | all 0 |
| **-30.0** | **149** | **4.97** | **baseline** | **all 0** |
| **-40.0** | **132** | **4.40** | **-11%** | **all 0** |

## Classification Comparison

| Category | -20 /g | -30 /g | -40 /g |
|----------|--------|--------|--------|
| bellibolt_attack_probably_correct | 2.60 | 2.53 | 2.47 |
| kw_f0007_range_game_flow | 1.10 | 1.27 | **1.00** |
| bb_f0007_range_no_retreat | 0.43 | 0.20 | 0.43 |
| bb_240_259 | 0.43 | 0.27 | 0.37 |
| wt_game_flow | 0.37 | 0.37 | **0.10** |
| kw_120_179 | 0.23 | 0.23 | **0.03** |

## Analysis

### -40.0 is promising

- anomalies_total -11% vs baseline
- kw_f0007_range_game_flow: 1.27 → 1.00 (-21%)
- wt_game_flow: 0.37 → 0.10 (-73%)
- Safety all 0

### -20.0 is worse

- anomalies_total +4% vs baseline
- Confirms that weakening attack suppression is counterproductive

### Trend reversal from Run 002

| Run | -40 vs -30 |
|-----|------------|
| Run 002 (no retreat_bonus) | +9% (worse) |
| **This run (retreat_bonus=1400)** | **-11% (better)** |

The interaction with retreat_bonus=1400 reversed the -40 trend. Stronger attack suppression now helps because the retreat pivot is more active.

## Recommendation

**-40.0 を 50g 検証候補にする。** ただし 30g は分散が大きいため、採用判断はまだしない。

## Next Step

1. attack_suppress_penalty=-40 を 50g で検証
2. 改善が維持されれば 200g へ
3. 30g だけで採用しない（Level 6 で 2 回実証済み）
