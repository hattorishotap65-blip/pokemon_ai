# Level 6: Weight Search Validation 50g

## Candidate

adv=0.3, energy=7.0 (30g 探索で最有望だった候補)

## 50g vs 50g Results

| Metric | Baseline (adv=0.4, e=5.0) | Candidate (adv=0.3, e=7.0) | Delta |
|--------|--------------------------|---------------------------|-------|
| anomalies_total | 5.44/g | 5.54/g | **+0.10** |
| attack_available_but_no_attack | 0 | **0** | safe |
| end_when_attack_available | 0 | **0** | safe |
| retreat_when_attack_available | 0 | **0** | safe |

### Classification Breakdown

| Category | Baseline | Candidate | Delta |
|----------|----------|-----------|-------|
| bellibolt_attack_probably_correct | 2.40/g | 2.84/g | +0.44 |
| kw_f0007_range_game_flow | 1.84/g | 1.50/g | -0.34 |
| bb_240_259_no_actionable_fix | 0.60/g | 0.30/g | -0.30 |
| bb_f0007_range_no_retreat | 0.46/g | 0.48/g | +0.02 |
| wt_game_flow_no_actionable_fix | 0.06/g | 0.22/g | +0.16 |
| kw_120_179_no_actionable_fix | 0.08/g | 0.18/g | +0.10 |

## Decision

**hold**

### 理由

1. **Safety all 0** — 安全性は問題なし
2. **anomalies_total +0.10/g** — 本質的に flat（改善なし）
3. **30g では -17% に見えたが、50g では +2%** — 30g の結果はゲーム分散
4. bellibolt_attack_probably_correct が +0.44/g 増加 — BB 正当攻撃が増えている（advantage weight を下げたことで BB 攻撃選択が変わった可能性）
5. wt_game_flow が +0.16 微増 — Wattrel がアクティブになるケースがわずかに増加

### 30g vs 50g の乖離

| Scale | adv=0.3 e=7.0 (/g) | vs baseline |
|-------|---------------------|-------------|
| 30g | 4.03 | -17% |
| **50g** | **5.54** | **+2%** |

30g の探索結果は小サンプル分散であり、50g では改善が消失した。

## Conclusion

- **adv=0.3 e=7.0 は採用候補から外す**
- **200g 検証は不要** — 50g で改善が消失しているため
- **現在のデフォルト値 (adv=0.4, e=5.0) を維持**
- **探索範囲を広げるべきか**: 現時点では不要。advantage_weight の微調整よりも、他のアプローチ（新しい重みの追加、ルール改善等）を検討すべき

## weights.json

**元の値に復元済み。**

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| data/weights.json | **復元済み** (adv=0.4, e=5.0) |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level6_weight_search_validation_50g.md | 新規 |
| reports/level6_weight_search_validation_50g.json | 新規 |
