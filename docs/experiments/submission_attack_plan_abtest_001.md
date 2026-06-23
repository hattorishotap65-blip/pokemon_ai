# Submission Attack Plan A/B Test 001

## Purpose

#134 の安全候補に対して、attack_plan.py を提出物に含めた場合にスコアが変わるか検証する。

## Baseline A (no attack_plan)

- #134 current state
- attack_plan.py excluded, attack_plan_bonus = 0
- params.py included, default_params.json included
- ML disabled

## Candidate B (attack_plan included)

- attack_plan.py included, attack_plan_bonus enabled
- params.py included, default_params.json included
- ML disabled

## 50g Results (start_game=112000, same seed)

| Metric | A: no attack_plan | B: attack_plan included |
|--------|-------------------|------------------------|
| Games | 50 | 50 |
| P0 wins | 27 | 24 |
| P1 wins | 23 | 26 |
| Errors | **0** | **0** |
| Timeouts | **0** | **0** |
| Total score | 40 | -20 |
| Score/game | +0.80 | -0.40 |
| Avg ms/game | 3909 | 4362 |

## 100g Results (start_game=112000, same seed)

| Metric | A: no attack_plan | B: attack_plan included |
|--------|-------------------|------------------------|
| Games | 100 | 100 |
| P0 wins | 45 | 52 |
| P1 wins | 55 | 48 |
| Errors | **0** | **0** |
| Timeouts | **0** | **0** |
| Total score | -100 | 40 |
| Score/game | -1.00 | **+0.40** |
| Avg ms/game | 4152 | 5238 |

## Analysis

### Score comparison

| Scale | A score/game | B score/game | Delta |
|-------|-------------|-------------|-------|
| 50g | +0.80 | -0.40 | -1.20 |
| 100g | -1.00 | **+0.40** | **+1.40** |

Self-play のため score は 0 周辺でブレる。50g と 100g で方向が逆転しており、
attack_plan_bonus の有無による明確な差は 100g でも統計的に不十分。

### Safety

- 両方とも errors=0, timeouts=0
- 100g B で P0=52/P1=48 と正常範囲

### Performance

- B は A より約 +1000ms/game 遅い（attack_plan 生成 + scoring コスト）

### 81461232 Regression Check

- B (attack_plan included) 100g で errors=0, timeouts=0
- 大規模な挙動悪化は確認されなかった
- ただし個別ログの詳細確認は未実施

## Decision

**Reject attack_plan inclusion for now**

理由:
1. 100g A/B で方向が一貫しない（50g: A優位、100g: B優位）
2. attack_plan_bonus の効果が self-play ブレの範囲に収まる
3. B は約 +1000ms/game のオーバーヘッド
4. #134 の安全候補を変更するリスクに見合う改善が確認できない
5. attack_plan.py を含めないことで 81461232 型の regression リスクも排除

## Next Steps

1. #134 を安全候補としてマージ・提出
2. attack_plan_bonus は将来的にチューニング後に再検討
3. 対戦相手が変わる本番環境でのスコアは self-play と異なる可能性あり
