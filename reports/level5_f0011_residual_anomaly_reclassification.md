# F0011: Residual Anomaly Reclassification

## Summary

200g (F0007 適用後 main) の残存 anomaly 998件を再分類。

| Category | Count | % | /game |
|----------|-------|---|-------|
| **B: no_fix_needed** | **551** | **55.2%** | **2.75** |
| **C: no_actionable_fix (game flow)** | **447** | **44.8%** | **2.23** |
| A: real_fix_candidate | 0 | 0% | 0 |
| D: logging_insufficient | 0 | 0% | 0 |
| E: classifier_false_positive | 0 | 0% | 0 |

## Key Finding

**修正すべき anomaly は 0件。** 全 998件が「妥当な行動」または「ゲーム展開上修正不可」。

## Category Details

### B: no_fix_needed (551件, 55.2%)

Bellibolt ex (230) が Voltorb 推定打点 (<=220) 以上で攻撃 → 妥当。F0004 確認済み。

### C: no_actionable_fix_game_flow (447件, 44.8%)

Voltorb の方が高打点だが、retreat / pivot では解決できないもの。

| Sub-reason | Count | 説明 |
|-----------|-------|------|
| kw_f0007_range_game_flow | 260 | KW active, VT>=180 だが F0007 pivot 後もゲーム展開で再発 |
| bb_240_259_proven_unreachable | 96 | BB 240-259 は F0009/F0010 で証明済み: pivot すると下流悪化 |
| bb_f0007_range_but_no_retreat | 37 | BB active, VT>=260 だが retreat option なし |
| wt_game_flow | 31 | Wattrel active, retreat 不可 or ゲーム展開 |
| kw_120_179_proven_unreachable | 23 | KW 120-179 は F0009 で証明済み: pivot 効果なし |

### A: real_fix_candidate (0件)

なし。

### D: logging_insufficient (0件)

なし。

### E: classifier_false_positive (0件)

F0005 の detector 修正で解消済み。

## Analysis

### なぜ C が 447件も残るか

1. **kw_f0007_range_game_flow (260件)**: F0007 pivot (+1100) は発火するが、**同一ゲームの別ターンで KW が再びアクティブになる**。pivot は 1 ターンの問題を解決するが、ゲーム全体での KW→Active 遷移を防げない。
2. **bb_240_259 (96件)**: F0009/F0010 で実証済み — BB 230 と VT 240-259 の打点差 (max 29) が retreat cost に見合わない。
3. **retreat なし (37+31件)**: 交代手段自体がない。

### F0007 の効果は限定的だが最大限

F0007 前の baseline では bb_over_voltorb_high_damage は 0.76/g → F0008 200g で 0.67/g に改善。これ以上の改善は pivot アプローチの限界。

## Final Judgment

**behavior 修正を止め、classifier / logger / report 整備に進む**

### 理由

1. **real_fix_candidate が 0件** — 修正すべき anomaly が存在しない
2. 残り 447件は全てゲーム展開上の構造的制約 — パラメータ調整では解決不可
3. F0009 (一律) / F0010 (KO条件) とも rejected — pivot 強化は逆効果
4. 551件は no_fix_needed — 現在の Bellibolt 攻撃判断が妥当

### 推奨する次のアクション

| Priority | Action | 目的 |
|----------|--------|------|
| 1 | classifier を更新して C を no_fix_needed に統合 | anomaly 数を実態に合わせる |
| 2 | anomaly report の「修正候補」から C を除外 | 不要な修正提案を減らす |
| 3 | logger にベンチ詳細（各ポケモンの energy）を追加 | 将来の判断精度向上 |
| 4 | Level 5 を完了とし、Level 6 検討に移行 | PDCA サイクルの次段階 |

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level5_f0011_residual_anomaly_reclassification.md | 新規 |
| reports/level5_f0011_residual_anomaly_reclassification.json | 新規 |
