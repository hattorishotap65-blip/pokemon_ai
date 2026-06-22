# ML Weight Search 001

## Purpose

Outcome-weighted trained weights を元に mutation search を小規模実行し、
評価指標と探索手順を検証した。候補 weights の本番適用は行わない。

## Environment

- Base branch: main (PR #115 merged)
- Base weights: `artifacts/ml_policy_weights_outcome_weighted.json`
- Search runner: `experiments/search_ml_weights.py`
- Evaluation runner: `experiments/evaluate_ml_weights.py`
- Date: 2026-06-23

## Search Config (5g eval)

| Parameter | Value |
|-----------|-------|
| iterations | 1 |
| mutations_per_iteration | 3 |
| mutation_rate | 0.2 |
| mutation_scale | 0.1 |
| seed | 42 |
| n | 5 |
| start_game | 88000 |
| mode | hybrid |

## 5g Results (skip-baseline)

| candidate | verdict | wins | losses | errors | timeouts | safety_diff |
|-----------|---------|------|--------|--------|----------|-------------|
| candidate_0001 | neutral | 4 | 1 | 0 | 0 | 0 |
| candidate_0002 | neutral | - | - | 0 | 0 | 0 |
| candidate_0003 | neutral | - | - | 0 | 0 | 0 |

Note: 5g skip-baseline のため score_available=false。
wins/losses は candidate のみの値（baseline 比較なし）。

## 30g Follow-up (candidate_0001, with baseline)

| metric | baseline | candidate | delta |
|--------|----------|-----------|-------|
| games | 30 | 30 | - |
| wins | 15 | 18 | +3 |
| losses | 15 | 12 | -3 |
| draws | 0 | 0 | 0 |
| errors | 0 | 0 | 0 |
| timeouts | 0 | 0 | 0 |
| avg_selections | 177.6 | 187.8 | +10.2 |
| avg_ms | 4025 | 4378 | +353 |
| safety_total_diff | - | - | 0 |
| verdict | - | - | candidate_neutral |

Note: score_available=false（run_matches_real.py に score 行なし）のため
verdict は neutral。win/loss は +3/-3 で改善傾向だが、30g では統計的有意差なし。

## Interpretation

- 5g は統計的ブレが大きく採用判断には使えない
- 30g の candidate_0001 は win +3 / loss -3 で改善傾向だが有意差には不十分
- score_available=false のため score_per_game 比較ができていない
  - run_matches_real.py に score 出力行を追加すれば改善可能
- errors=0, timeouts=0, safety_total_diff=0 で安全性は維持
- avg_ms +353ms は mutation weights 読み込み + ML scoring のオーバーヘッド

## Next Steps

1. run_matches_real.py に score 行を追加し score_per_game 比較を有効化
2. mutation_scale を変えた探索（0.05, 0.2）で候補の多様性を検証
3. 100g 評価で統計的有意差を確認
4. 良い候補があれば実験用 config として保存を検討
5. runtime default は変更しない
