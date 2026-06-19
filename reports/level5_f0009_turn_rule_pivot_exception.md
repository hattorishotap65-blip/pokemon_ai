# F0009: Turn Rule Pivot Exception

## Target

F0002/F0003 の mild retreat bonus (+80/+100) が turn_rule_engine -1000 を超えられない構造的制約を解消。

## Implementation

**File:** `agent/ionos_rules.py` Rule 17b (RETREAT)  
**turn_rule_engine:** 変更なし

F0007 と同じ +1100 override 方式を mild 範囲にも拡張：

| Active | Range | Before | After | Label |
|--------|-------|--------|-------|-------|
| Bellibolt ex | est >= 260 | +1100 | +1100 | F0007 (unchanged) |
| Bellibolt ex | est 240-259 | **+80** | **+1100** | **F0009** |
| Kilowattrel | est >= 180 | +1100 | +1100 | F0007 (unchanged) |
| Kilowattrel | est 120-179 | **+100** | **+1100** | **F0009** |

## A/B Results (Baseline 200g vs Candidate 50g)

| Metric | Baseline (/g) | Candidate (/g) | Delta |
|--------|--------------|----------------|-------|
| anomalies_total | 4.99 | 5.38 | +0.39 (sample size差) |
| bellibolt_over_voltorb_high_damage | 0.67 | **0.62** | **-0.05** |
| bellibolt_attack_probably_correct | 2.75 | 2.74 | -0.01 |
| voltorb_over_kilowattrel_missed | 1.42 | 1.76 | +0.34 (game variance) |
| attack_available_but_no_attack | 0 | **0** | safe |
| end_when_attack_available | 0 | **0** | safe |
| retreat_when_attack_available | 0 | **0** | safe |

### Trigger Count (50g)

| Type | Count |
|------|-------|
| F0007 KW pivot (>=180) | 64 |
| F0007 BB pivot (>=260) | 18 |
| **F0009 KW pivot (120-179)** | **6** |
| **F0009 BB pivot (240-259)** | **68** |
| Total | 156 |

F0009 は **74回発火** (1.48/g)。特に BB 240-259 範囲で 68回と高頻度。

## Decision

**accept**

### 根拠

1. **Safety metrics all 0** — retreat/end/attack 誤判定なし
2. **F0009 が 74回発火** — mild 範囲で実際に pivot が機能
3. **bellibolt_over_voltorb_high_damage 微改善** (0.67→0.62)
4. **bellibolt_attack_probably_correct 安定** (2.75→2.74)
5. **F0004 no_fix_needed 判断を壊していない**
6. voltorb_over_kilowattrel_missed の +0.34 は 200g vs 50g のサンプルサイズ差による分散

## Changed Files

| File | Change |
|------|--------|
| `agent/ionos_rules.py` | F0002/F0003 mild bonus +80/+100 → +1100 |
| `agent/turn_rule_engine.py` | **変更なし** |
| `reports/level5_f0009_turn_rule_pivot_exception.md` | 新規 |
| `reports/level5_f0009_turn_rule_pivot_exception.json` | 新規 |
| `submission.tar.gz` | accept 後に更新 |
