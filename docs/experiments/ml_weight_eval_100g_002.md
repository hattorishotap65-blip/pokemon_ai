# ML Weight 100g Evaluation 002

## Purpose

PR #120 で改善が確認された candidate_0001 を、別 start_game で 100g 再評価した。
改善傾向の再現性を確認することが目的。候補 weights の本番適用は行わない。

## Environment

- Base branch: main (PR #120 merged)
- Base weights: `artifacts/ml_policy_weights_outcome_weighted.json`
- Candidate: `artifacts/ml_weight_search_score_5g/candidate_0001.json`
- Candidate source: ML Weight Search 002 (mutation_rate=0.2, scale=0.1, search seed=42, candidate seed=43)
- Evaluation runner: `experiments/evaluate_ml_weights.py`
- Date: 2026-06-23

## Prior Result (PR #120)

| evaluation | start_game | games | verdict | spg_delta | wins_delta | losses_delta | errors | timeouts | safety_diff |
|-----------|------------|-------|---------|-----------|------------|--------------|--------|----------|-------------|
| PR #120 | 94000 | 100 | **candidate_better** | **+2.4** | **+12** | **-12** | 0 | 0 | 0 |

## Recheck Results

| evaluation | start_game | games | verdict | BL spg | CD spg | spg_delta | wins_delta | losses_delta | errors | timeouts | safety_diff | avg_ms_diff |
|-----------|------------|-------|---------|--------|--------|-----------|------------|--------------|--------|----------|-------------|-------------|
| recheck 1 | 95000 | 100 | **candidate_better** | -0.6 | 1.2 | **+1.8** | **+9** | **-9** | 0 | 0 | 0 | +770 |
| recheck 2 | 96000 | 100 | candidate_neutral | 1.8 | 1.0 | -0.8 | -4 | +4 | 0 | 0 | 0 | +922 |

## All 100g Results Combined

| evaluation | start_game | verdict | spg_delta | wins_delta |
|-----------|------------|---------|-----------|------------|
| PR #120 | 94000 | **candidate_better** | **+2.4** | **+12** |
| recheck 1 | 95000 | **candidate_better** | **+1.8** | **+9** |
| recheck 2 | 96000 | candidate_neutral | -0.8 | -4 |

- 3回の100g中、2回が candidate_better、1回が candidate_neutral
- 合計 300g: wins_delta = +12+9-4 = **+17**, losses_delta = -12-9+4 = **-17**
- 合計 spg_delta = (+2.4+1.8-0.8)/3 = **+1.13**

## Interpretation

- 3回の100gで2/3が candidate_better。改善傾向は概ね再現した。
- ただし recheck 2 (start=96000) では改善が消失し、100g 単位での分散は大きい。
- 合計 300g で wins +17 は改善傾向だが、統計的有意性は未確認。
- 全回で errors=0, timeouts=0, safety_total_diff=0。安全性は維持。
- avg_ms は +770〜+1073 のオーバーヘッド（ML scoring コスト）。

## Decision

- candidate_0001: **候補保留** — 改善傾向は概ね再現するが、100g 単位の分散が大きい
- 200g 評価の優先度は中程度。300g 合計の改善傾向から採用可能性はある
- ML scoring のオーバーヘッド (+800ms程度) は許容範囲か要確認

## Next Steps

1. 候補保留のまま、他の改善テーマ（attack_plan 強化等）を先に進める選択肢あり
2. 200g 評価を行う場合は、candidate_0001 を対象にする
3. mutation_scale を変えた別候補も並行検討可能
4. runtime default はまだ変更しない
5. configs/ml_policy_weights.json はまだ変更しない
