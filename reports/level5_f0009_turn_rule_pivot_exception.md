# F0009: Turn Rule Pivot Exception — KW-Only Validation

## Summary

F0009 full (BB+KW) は hold → BB 240-259 を revert し、KW 120-179 のみで 200g 再検証。

## Current Implementation

| Active | Range | Bonus | Source |
|--------|-------|-------|--------|
| Bellibolt ex | est >= 260 | +1100 | F0007 (maintained) |
| Bellibolt ex | est 240-259 | **+80** | F0003 mild (**reverted from F0009**) |
| Kilowattrel | est >= 180 | +1100 | F0007 (maintained) |
| Kilowattrel | est 120-179 | **+1100** | **F0009 KW-only** |

## F0009 Full Result (BB+KW, 200g vs 200g)

**Decision: hold** — BB 240-259 の +1100 が以下を悪化させた:
- bellibolt_over_voltorb_high_damage: +22%
- voltorb_over_wattrel_missed: +127%

→ BB 240-259 は revert。

## F0009 KW-Only Result (200g vs 200g)

| Metric | Baseline (F0007) | Candidate (F0007+F0009 KW) | Delta |
|--------|-----------------|---------------------------|-------|
| bellibolt_attack_probably_correct | 2.75/g | 2.74/g | -0.01 |
| bellibolt_over_voltorb_high_damage | 0.67/g | 0.70/g | +0.03 |
| **voltorb_over_kilowattrel_missed** | **1.42/g** | **1.55/g** | **+0.14** |
| voltorb_over_wattrel_missed | 0.15/g | 0.12/g | -0.04 |
| attack_available_but_no_attack | 0 | **0** | safe |
| end_when_attack_available | 0 | **0** | safe |
| retreat_when_attack_available | 0 | **0** | safe |

### Trigger Count (200g)

| Type | Count | /game |
|------|-------|-------|
| F0009 KW (120-179) | 36 | 0.18 |
| F0007 KW (>=180) | 197 | 0.98 |
| F0007 BB (>=260) | 188 | 0.94 |
| F0003 BB mild (240-259) | 353 | 1.76 |

### Per-Batch Consistency

| Batch | Total | bb_high/g | kw_miss/g | wt_miss/g |
|-------|-------|-----------|-----------|-----------|
| g32xx | 250 | 0.94 | 1.34 | 0.14 |
| g33xx | 290 | 0.76 | 1.84 | 0.10 |
| g34xx | 235 | 0.80 | 1.28 | 0.10 |
| g35xx | 249 | 0.30 | 1.76 | 0.12 |

## Decision

**hold**

### 根拠

**良い点:**
- Safety all 0
- BB revert により bellibolt_over_voltorb_high_damage と voltorb_over_wattrel_missed の悪化が解消
- voltorb_over_wattrel_missed は微改善 (0.15→0.12)

**懸念点:**
- voltorb_over_kilowattrel_missed が +0.14/g (1.42→1.55)
- F0009 KW trigger は 36回/200g (0.18/g) と低頻度
- 改善効果が不明確

### 分析

KW 120-179 の F0009 pivot は 200g で 36回しか発火せず、効果が小さい。voltorb_over_kilowattrel_missed が微増しているのは、KW→Voltorb retreat が発生してもゲーム展開変化で別のターンに KW 攻撃が増えた可能性がある。

F0009 KW-only は安全だが改善効果が限定的。accept するか revert するかは判断待ち。

## Changed Files

| File | Change |
|------|--------|
| `agent/ionos_rules.py` | BB 240-259 reverted to +80, KW 120-179 kept at +1100 |
| `reports/level5_f0009_turn_rule_pivot_exception.md` | 更新 |
| `reports/level5_f0009_turn_rule_pivot_exception.json` | 更新 |
| `submission.tar.gz` | 再生成済み |
