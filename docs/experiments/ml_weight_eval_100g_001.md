# ML Weight 100g Evaluation 001

## Purpose

PR #118 で改善傾向があった candidate_0001 / candidate_0002 を、
PR #119 の verdict 修正後に 100g で再評価した。
候補 weights の本番適用ではなく、100g でも改善傾向が残るか確認することが目的。

## Environment

- Base branch: main (PR #119 merged)
- Base weights: `artifacts/ml_policy_weights_outcome_weighted.json`
- Candidate source: `artifacts/ml_weight_search_score_5g/` (ML Weight Search 002)
- Evaluation runner: `experiments/evaluate_ml_weights.py`
- Date: 2026-06-23

## Score Definition

| result | score |
|--------|-------|
| win (p0) | +10 |
| loss (p1) | -10 |
| draw/other | 0 |
| timeout/error | -20 |

## Candidate Source

| candidate | source | 30g result (Search 002) |
|-----------|--------|------------------------|
| candidate_0001 | ml_weight_search_score_5g/candidate_0001.json | wins +4, losses -4, spg +2.67 |
| candidate_0002 | ml_weight_search_score_5g/candidate_0002.json | wins +4, losses -4, spg +2.67 |

## 100g Results

### candidate_0001

| metric | baseline | candidate | delta |
|--------|----------|-----------|-------|
| games | 100 | 100 | - |
| wins | 53 | 65 | **+12** |
| losses | 47 | 35 | **-12** |
| score_per_game | 0.6 | 3.0 | **+2.4** |
| errors | 0 | 0 | 0 |
| timeouts | 0 | 0 | 0 |
| safety_total_diff | - | - | 0 |
| avg_ms | - | - | +1073 |
| score_available | true | true | - |
| **verdict** | - | - | **candidate_better** |

### candidate_0002

| metric | baseline | candidate | delta |
|--------|----------|-----------|-------|
| games | 100 | 100 | - |
| wins | 52 | 53 | +1 |
| losses | 48 | 47 | -1 |
| score_per_game | 0.4 | 0.6 | +0.2 |
| errors | 0 | 0 | 0 |
| timeouts | 0 | 0 | 0 |
| safety_total_diff | - | - | 0 |
| avg_ms | - | - | -782 |
| score_available | true | true | - |
| **verdict** | - | - | candidate_neutral |

## Summary

| candidate | 5g spg | 30g spg_delta | 100g spg_delta | 100g wins_delta | 100g verdict |
|-----------|--------|---------------|----------------|-----------------|--------------|
| 0001 | +10.0 | +2.67 | **+2.4** | **+12** | **candidate_better** |
| 0002 | +6.0 | +2.67 | +0.2 | +1 | candidate_neutral |

## Interpretation

- **candidate_0001**: 100g でも明確な改善。wins +12, spg +2.4。
  30g の +2.67 と 100g の +2.4 が一貫している。
  safety regression なし、errors/timeouts なし。
  avg_ms +1073 のオーバーヘッドあり（ML scoring コスト）。
- **candidate_0002**: 100g では改善がほぼ消失。wins +1, spg +0.2。
  30g では +2.67 だったが 100g で統計ブレの範囲に収まった。

## Decision

- candidate_0001: **追加評価する** — 別 start_game で 100g 再評価し再現性を確認
- candidate_0002: **候補保留** — 100g で改善消失のため追加評価の優先度は低い

## Next Steps

1. candidate_0001 を別 start_game で 100g 再評価（再現性確認）
2. 再現すれば 200g でも確認
3. 2回の 100g で一貫して改善する候補のみ、実験用 weights 保存を検討
4. runtime default はまだ変更しない
5. configs/ml_policy_weights.json はまだ変更しない
