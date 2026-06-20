# Level 6: energy_to_plan_bonus=4.0 Validation 50g

## Candidate

energy_to_plan_bonus=4.0 (Run 002 で最有望、30g で 4.20/g)

## 50g vs 50g Results

| Metric | Baseline (e=5.0) | Candidate (e=4.0) | Delta |
|--------|-----------------|-------------------|-------|
| **anomalies_total** | **4.48/g** | **4.96/g** | **+0.48 worsened** |
| bellibolt_attack_probably_correct | 2.08/g | 2.58/g | +0.50 |
| kw_f0007_range_game_flow | 1.30/g | 1.72/g | +0.42 |
| bb_240_259_no_actionable_fix | 0.42/g | 0.24/g | -0.18 |
| wt_game_flow_no_actionable_fix | 0.28/g | 0.14/g | -0.14 |
| Safety (all 4) | 0 | **0** | safe |

## Decision

**hold / not adopted**

### 理由

1. **anomalies_total +0.48/g** — 改善ではなく悪化
2. **30g → 50g パターン再現**: Run 001 (adv=0.3 e=7.0) と同じく、30g の改善が 50g で消失
3. Safety は all 0 で問題なし
4. bellibolt_attack_probably_correct +0.50 と kw_f0007_range +0.42 が増加

### 30g vs 50g の比較

| Scale | energy=4.0 (/g) | vs baseline |
|-------|-----------------|-------------|
| 30g (Run 002) | 4.20 | -14% |
| **50g** | **4.96** | **+11%** |

Run 001 と同じパターン。**30g の探索結果は分散であり、50g では改善が消失。**

## Level 6 Weight Search 総括

| Candidate | 30g | 50g | 判定 |
|-----------|-----|-----|------|
| adv=0.3 e=7.0 (Run 001) | -17% | +2% | not adopted |
| **e=4.0 (Run 002)** | **-14%** | **+11%** | **not adopted** |

**2回連続で 30g の有望候補が 50g で否定された。** 現在の重みパラメータ空間では、デフォルト値が既に安定的な最適付近にある可能性が高い。

## Next Step

- **200g 検証は不要** — 50g で悪化しているため
- **デフォルト値 (e=5.0) を維持**
- **Level 6 重み探索はここで一旦完了とすることを推奨** — 小範囲の微調整では改善が見込めない
- 次に改善を狙うなら、新しい重みパラメータの追加（現在外出しされていないスコア）、または異なるアプローチ（ルール構造変更）が必要

## weights.json

**元の値に復元済み。**

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| data/weights.json | **復元済み** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level6_energy_bonus_4_validation_50g.md | 新規 |
| reports/level6_energy_bonus_4_validation_50g.json | 新規 |
