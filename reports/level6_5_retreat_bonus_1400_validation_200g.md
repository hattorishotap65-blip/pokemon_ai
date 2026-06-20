# Level 6.5: retreat_to_better_attacker_bonus=1400 Validation 200g

## 200g vs 200g Results

| Metric | Baseline (1100) | Candidate (1400) | Delta |
|--------|----------------|-----------------|-------|
| **anomalies_total** | **5.43/g** | **4.97/g** | **-0.46 (-8.5%)** |
| **kw_f0007_range_game_flow** | **1.66/g** | **1.10/g** | **-0.55 (-33%)** |
| bellibolt_attack_probably_correct | 2.73/g | 2.25/g | -0.49 |
| bb_f0007_range_no_retreat | 0.27/g | 0.57/g | +0.30 |
| wt_game_flow | 0.15/g | 0.38/g | +0.23 |
| bb_240_259 | 0.46/g | 0.54/g | +0.08 |
| Safety (all 4) | 0 | **0** | safe |
| F0007 triggers | 2.42/g | 2.19/g | stable |

## 30g → 50g → 200g Consistency

| Scale | 1400 vs baseline | Trend |
|-------|-----------------|-------|
| 30g | **-12%** | initial |
| 50g | **-18%** | expanded |
| **200g** | **-8.5%** | **stable** |

**200g でも改善が維持。** 50g の -18% からはやや収束したが、30g → 50g → 200g で一貫して改善。

## Per-Batch Consistency (Candidate 200g)

| Batch | /game | kw_game_flow | bb_no_retreat |
|-------|-------|-------------|---------------|
| g80xx | 4.92 | 1.18 | 0.64 |
| g81xx | 4.54 | 0.92 | 0.44 |
| g82xx | 5.52 | 1.24 | 0.68 |
| g83xx | 4.90 | 1.08 | 0.52 |

バッチ間の分散はあるが、全バッチでbaseline (5.43) 以下。

## Side Effects Analysis

### bb_f0007_range_no_retreat +0.30/g

50g と同じ増加幅。**安定した副作用**。retreat をより試みるが手段がないケースが増える。実際の挙動は retreat option がなければ従来通り攻撃するため、safety に影響なし。

### wt_game_flow +0.23/g

200g で新たに見えた副作用。retreat bonus を上げたことでゲーム展開が変わり、Wattrel がアクティブになるケースが微増。ただし safety metrics は 0 のまま。

## Decision

**採用 PR 推奨**

### 根拠

1. **Safety all 0** (200g) — 安全性は完全
2. **anomalies_total -8.5%** — 200g でも明確な改善
3. **kw_f0007_range_game_flow -33%** — 最大の課題が大幅改善
4. **30g → 50g → 200g で一貫して改善** — Level 6 初の安定候補
5. **F0007 triggers 安定** (2.42 → 2.19) — 不自然な増加なし
6. 副作用 (bb_no_retreat +0.30, wt_game_flow +0.23) は安全で許容範囲

## weights.json

**元の値 (1100.0) に復元済み。**

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| data/weights.json | **復元済み (1100.0)** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level6_5_retreat_bonus_1400_validation_200g.md | 新規 |
| reports/level6_5_retreat_bonus_1400_validation_200g.json | 新規 |
