# ML Weight Search 002

## Purpose

PR #117 の score 出力追加後、score_available=true の状態で mutation search を再実行した。
score_per_game による候補比較が機能するか検証することが目的。候補 weights の本番適用は行わない。

## Environment

- Base branch: main (PR #117 merged)
- Base weights: `artifacts/ml_policy_weights_outcome_weighted.json`
- Search runner: `experiments/search_ml_weights.py`
- Evaluation runner: `experiments/evaluate_ml_weights.py`
- Date: 2026-06-23

## Score Definition

| result | score |
|--------|-------|
| win (p0) | +10 |
| loss (p1) | -10 |
| draw/other | 0 |
| timeout/error | -20 |

## Score Availability Check (5g pre-check)

| item | result |
|------|--------|
| score_available | **true** |
| baseline total_score | -10.0 |
| candidate total_score | 10.0 |
| baseline score_per_game | -2.0 |
| candidate score_per_game | 2.0 |
| delta score_per_game | +4.0 |

## Search Config

| Parameter | Value |
|-----------|-------|
| iterations | 2 |
| mutations_per_iteration | 3 |
| mutation_rate | 0.2 |
| mutation_scale | 0.1 |
| seed | 42 |
| n | 5 |
| start_game | 92000 |
| mode | hybrid |

## 5g Results

| candidate | verdict | wins | losses | spg | spg_delta | errors | timeouts | safety_diff |
|-----------|---------|------|--------|-----|-----------|--------|----------|-------------|
| 0001 | neutral | 5 | 0 | 10.0 | +10.0 | 0 | 0 | 0 |
| 0002 | neutral | 4 | 1 | 6.0 | +6.0 | 0 | 0 | 0 |
| 0003 | neutral | 2 | 3 | -2.0 | -2.0 | 0 | 0 | 0 |
| 0004 | neutral | 2 | 3 | -2.0 | -2.0 | 0 | 0 | 0 |
| 0005 | neutral | 1 | 4 | -6.0 | -6.0 | 0 | 0 | 0 |
| 0006 | neutral | 2 | 3 | -2.0 | -2.0 | 0 | 0 | 0 |

Note: skip-baseline のため score_pct=0。spg_delta は candidate の score_per_game そのもの。

## 30g Follow-up

### candidate_0001

| metric | baseline | candidate | delta |
|--------|----------|-----------|-------|
| games | 30 | 30 | - |
| wins | 11 | 15 | **+4** |
| losses | 19 | 15 | **-4** |
| score_per_game | -2.67 | 0.0 | **+2.67** |
| errors | 0 | 0 | 0 |
| timeouts | 0 | 0 | 0 |
| safety_total_diff | - | - | 0 |
| avg_ms | 4624 | 4695 | +71 |
| verdict | - | - | candidate_worse* |

*verdict=candidate_worse は score_pct 計算がBL負値で反転する既知問題。
実際の delta score_per_game=+2.67 で候補の方が改善。

### candidate_0002

| metric | baseline | candidate | delta |
|--------|----------|-----------|-------|
| games | 30 | 30 | - |
| wins | 15 | 19 | **+4** |
| losses | 15 | 11 | **-4** |
| score_per_game | 0.0 | 2.67 | **+2.67** |
| errors | 0 | 0 | 0 |
| timeouts | 0 | 0 | 0 |
| safety_total_diff | - | - | 0 |
| avg_ms | 4362 | 4468 | +106 |
| verdict | - | - | candidate_neutral |

## Interpretation

- score_available=true により score_per_game 比較が機能した
- 5g の spg_delta はブレが大きく参考値（5g で ±10 振れる）
- 30g で候補 0001/0002 ともに wins +4, losses -4, spg +2.67
- 0 errors, 0 timeouts, 0 safety regression
- 両候補とも改善傾向だが、30g では統計的有意差に不十分
- score_pct 計算に BL 負値時の反転問題あり（次 PR で修正候補）

## Known Issues

- `compute_verdict` の `score_pct` 計算: BL score_per_game が負値のとき pct が反転し、
  実際にはスコア改善しているのに `candidate_worse` になる
- BL score_per_game=0 のとき pct=0 で常に neutral になる
- 修正候補: delta score_per_game の絶対値で判定する、または win_rate で補助判定

## Decision

- 今回の候補を採用するか: **追加評価する**
- 理由: 30g で改善傾向、ただし統計的有意差が不十分

## Next Steps

1. score_pct の BL 負値問題を修正
2. candidate_0001/0002 を 100g で再評価
3. 100g でも改善するなら実験用 weights として保存を検討
4. runtime default はまだ変更しない
