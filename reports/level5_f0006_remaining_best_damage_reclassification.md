# F0006: Remaining best_damage_attacker_not_selected Reclassification

## Summary

| Metric | Value |
|--------|-------|
| Games | 50 |
| Total best_damage_attacker_not_selected | 291 |
| → no_fix_needed | **153 (52.6%)** |
| → pivot_design_needed | **120 (41.2%)** |
| → no_actionable_fix_due_to_no_retreat | **18 (6.2%)** |
| → detector_refinement | 0 |

## Reclassification Results

| Category | Count | /game | Action |
|----------|-------|-------|--------|
| bellibolt_attack_probably_correct | 153 | 3.06 | **no_fix_needed** |
| pivot_to_better_attacker_candidate | 120 | 2.40 | **pivot_design_needed** |
| no_actionable_fix_due_to_no_retreat | 18 | 0.36 | retreat 不可（修正手段なし） |
| detector_refinement_candidate | 0 | 0.00 | — |

no_actionable_fix_due_to_no_retreat 内訳:

| Sub-category | Count |
|-------------|-------|
| kilowattrel_over_voltorb_remaining | 11 |
| wattrel_over_voltorb_remaining | 5 |
| bellibolt_over_voltorb_high_damage_remaining | 2 |

## Category Details

### 1. bellibolt_attack_probably_correct (153件) — no_fix_needed

- Bellibolt ex 230 >= Voltorb 推定打点（max 220）
- F0004 で no_fix_needed 確認済み
- **修正不要**

### 2. pivot_to_better_attacker_candidate (120件) — 構造的課題

retreat option が存在していたが、turn_rule_engine の -1000 retreat penalty により交代できなかった。

| Actual Attacker | Count |
|----------------|-------|
| Kilowattrel (271) | 91 |
| Bellibolt ex (269) | 29 |

Voltorb 推定打点分布:

| Range | Count |
|-------|-------|
| 120-159 | 1 |
| 160-199 | 11 |
| 200-239 | 40 |
| 240-279 | 52 |
| 280-319 | 16 |

**68件 (57%) が Voltorb 240+ で Bellibolt の 230 を上回る。** しかし retreat penalty -1000 のため交代不可。

これは F0002/F0003 と同じ構造的問題:
> turn_rule_engine が「攻撃可能なら retreat しない」を -1000 で強制。  
> より良いアタッカーへの pivot を例外として扱う仕組みがない。

### 3. no_actionable_fix_due_to_no_retreat (18件)

retreat option が存在しないため、Voltorb が高打点でも交代手段がなく、現在のアタッカーで攻撃するしかない。

| Sub-category | Count | 状況 |
|-------------|-------|------|
| kilowattrel_over_voltorb_remaining | 11 | KW 70 vs VT 180-300、retreat 不可 |
| wattrel_over_voltorb_remaining | 5 | Wattrel vs VT 120-160、retreat 不可 |
| bellibolt_over_voltorb_high_damage_remaining | 2 | BB 230 vs VT 240、retreat 不可 |

→ **修正手段なし**（retreat が使えない以上やむを得ない）

## F0003 閾値調査との関連

F0003 閾値調査で判明済み: retreat bonus を +1200 にすると `retreat_when_attack_available` が悪化する。  
今回の 120 件 (pivot_candidate) はすべて同じ構造的制約に起因。パラメータ調整では解決困難。

## 次にF0007として進めるべき候補

### 推奨: pivot_design_needed

120件の pivot_to_better_attacker_candidate に対し、turn_rule_engine に「pivot exception」を設計する。

設計案:
1. **turn_rule_engine に条件付き例外**: 攻撃可能でも、ベンチに明確に高打点のアタッカーがいる場合は retreat penalty を緩和
2. **Bellibolt 攻撃ペナルティ**: ionos_rules で Bellibolt 攻撃スコアを Voltorb 推定打点に応じて減点
3. **promote/switch 改善**: KO 後の TO_ACTIVE 選択時に Voltorb を優先

ただし、いずれもリスクがあるため A/B テスト必須。

### 優先しない候補

- kilowattrel/wattrel/bellibolt_remaining (18件): retreat 不可のためパラメータ修正では解決不可
- detector_refinement (0件): 現在の分類で問題なし

## 最終判断

**pivot_design_needed**

- 残件 291 のうち 153件 (52.6%) は **no_fix_needed**（Bellibolt 攻撃が妥当）
- 120件 (41.2%) は **pivot_design_needed**（retreat penalty -1000 によるブロック）
- 18件 (6.2%) は **no_actionable_fix_due_to_no_retreat**（retreat 手段自体がない）
- agent 本体は変更なし
- 次の F0007 で pivot_to_better_attacker の設計を検討すべき

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level5_f0006_remaining_best_damage_reclassification.md | 新規 |
| reports/level5_f0006_remaining_best_damage_reclassification.json | 新規 |
