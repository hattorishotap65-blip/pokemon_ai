# F0008: F0007 Extended Validation (200 games)

## Purpose

F0007 (pivot_to_better_attacker) が 200 ゲーム規模で安全かを検証する。50ゲーム A/B テストで bellibolt_over_voltorb_high_damage の微増が観測されたため、ゲーム分散か傾向かを確認。

## Test Conditions

- Agent: F0007 merge 後の main
- Games: **200** (4 batch x 50)
- Mode: self-play
- Errors: 0, Timeouts: 0

## Results (200 games)

### Classification

| Category | Count | /game |
|----------|-------|-------|
| bellibolt_attack_probably_correct | 551 | 2.75 |
| voltorb_over_kilowattrel_missed | 283 | 1.42 |
| bellibolt_over_voltorb_high_damage | 133 | 0.67 |
| voltorb_over_wattrel_missed | 31 | 0.15 |
| **Total** | **998** | **4.99** |

### Safety Metrics

| Metric | Value |
|--------|-------|
| attack_available_but_no_attack | **0** |
| end_when_attack_available | **0** |
| retreat_when_attack_available | **0** |
| ability_without_followup_attack | **0** |
| error_rate | **0%** |

### F0007 Trigger Count

| Type | Count | /game |
|------|-------|-------|
| F0007 KW pivot (est >= 180) | 209 | 1.04 |
| F0007 BB pivot (est >= 260) | 173 | 0.86 |
| F0002 KW mild (est 120-179) | 24 | 0.12 |
| F0003 BB mild (est 240-259) | 328 | 1.64 |
| **Total** | **734** | **3.67** |

### Per-Batch Consistency

| Batch | Total | bb_high/g | kw_miss/g | bb_ok/g |
|-------|-------|-----------|-----------|---------|
| g23xx | 239 | 0.46 | 1.72 | 2.52 |
| g24xx | 260 | 0.66 | 1.28 | 2.82 |
| g25xx | 268 | 0.74 | 1.42 | 3.10 |
| g26xx | 231 | 0.80 | 1.24 | 2.58 |

bb_high（bellibolt_over_voltorb_high_damage）のバッチ間変動: 0.46〜0.80/g。標準的なゲーム分散の範囲。

## Comparison with Previous Measurements

| Metric (/game) | F0007前 baseline (50g) | F0007後 50g A/B | F0008 200g |
|----------------|----------------------|----------------|-----------|
| anomalies_total | 5.80 | 5.78 | **4.99** |
| voltorb_over_kilowattrel_missed | 2.02 | 2.00 | **1.42** |
| bellibolt_over_voltorb_high_damage | 0.76 | 1.10 | **0.67** |
| bellibolt_attack_probably_correct | 2.96 | 2.62 | **2.75** |

### bellibolt_over_voltorb_high_damage の推移

- F0007 前 baseline: **0.76/g**
- F0007 50g A/B: **1.10/g** (微増 → ゲーム分散の疑い)
- **F0008 200g: 0.67/g** (baseline 以下に安定)

→ **50g A/B での微増はゲーム分散と確定。** 200g では baseline 以下。

## Decision

**keep_f0007**

### 根拠

1. **Safety metrics 全て 0 (200g)** — retreat/end/attack 誤判定なし
2. **anomalies_total 4.99/g** — baseline 5.80 から **14% 改善**
3. **voltorb_over_kilowattrel_missed 1.42/g** — baseline 2.02 から **30% 改善**
4. **bellibolt_over_voltorb_high_damage 0.67/g** — baseline 0.76 以下に安定。50g A/B での 1.10 はゲーム分散
5. **F0007 pivot trigger 382回 (1.91/g)** — 実際に動作している
6. **F0002/F0003 mild trigger 352回 (1.76/g)** — 既存救済も維持
7. **error_rate 0%** — 全200ゲームでエラーなし

### F0007 閾値調整は不要

- BB pivot >=260: 適切（0.86/g trigger、安全に発火）
- KW pivot >=180: 適切（1.04/g trigger、安全に発火）
- 両方とも retreat_when_attack_available を 0 に維持

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level5_f0008_f0007_extended_validation.md | 新規（このレポート） |
| reports/level5_f0008_f0007_extended_validation.json | 新規 |

## Next Steps

- F0007 は **maintain**
- 残りの改善候補:
  - voltorb_over_kilowattrel_missed (1.42/g): KW pivot >=180 で拾えない 120-179 範囲。mild +100 では turn_rule -1000 を超えられない構造的制約
  - bellibolt_attack_probably_correct (2.75/g): no_fix_needed 確認済み (F0004)
  - bellibolt_over_voltorb_high_damage (0.67/g): BB pivot >=260 で拾えない 240-259 範囲。mild +80 の構造的制約
- これ以上のパラメータ改善は turn_rule_engine の構造的変更が必要
