# F0010: Conditional Voltorb Pivot — Rejected

## Final Decision: **reject**

## What Was Tested

F0009 の一律 pivot の代わりに、**Voltorb で相手 active を KO できる場合のみ** pivot を許可。

| Active | Range | Condition | Bonus |
|--------|-------|-----------|-------|
| Bellibolt ex | est 240-259 | Voltorb can KO (est >= opp_hp) | +1100 |
| Kilowattrel | est 120-179 | Voltorb can KO (est >= opp_hp) | +1100 |

F0009 との違い: F0009 は無条件 +1100、F0010 は KO 可能時のみ +1100。

## 200g vs 200g Results

| Metric | Baseline (F0007) | Candidate (F0010) | Delta |
|--------|-----------------|-------------------|-------|
| bellibolt_over_voltorb_high_damage | 0.67/g | 0.62/g | -0.04 |
| bellibolt_attack_probably_correct | 2.75/g | 2.61/g | -0.15 |
| **voltorb_over_kilowattrel_missed** | **1.42/g** | **1.62/g** | **+0.21 worsened** |
| **voltorb_over_wattrel_missed** | **0.15/g** | **0.27/g** | **+0.11 worsened** |
| Safety (all 4) | 0 | **0** | safe |

### Trigger Count (200g)

| Type | Count | /game |
|------|-------|-------|
| F0010 BB ko-pivot | 206 | 1.03 |
| F0010 KW ko-pivot | 36 | 0.18 |
| F0007 KW (>=180) | 215 | 1.07 |
| F0007 BB (>=260) | 76 | 0.38 |

## Why Rejected

1. **voltorb_over_kilowattrel_missed +0.21/g** — reject 条件に該当
2. **voltorb_over_wattrel_missed +0.11/g** — reject 条件に該当
3. F0010 BB ko-pivot が 206回と高頻度だが、retreat によるゲーム展開変化が下流 anomaly を増加させている
4. KO 条件を付けても、retreat → active 選択 → 攻撃の3ステップでゲーム flow が変わり、Wattrel がアクティブになるケースが増える

## Lessons Learned

F0009/F0010 共通の知見:

- **BB 240-259 への pivot（KO 条件の有無にかかわらず）は下流の anomaly を悪化させる**
- BB 230 と VT 240-259 の打点差（最大29）が retreat cost に見合わない
- retreat → ゲーム展開変化 → 他のアタッカーがアクティブになるケースが増加
- **KW → VT の mild 範囲 (120-179) は trigger 36回/200g と低頻度で効果判定困難**

## Current Agent State

F0007 のみ維持（BB >=260, KW >=180 の strong pivot）。F0010 の変更は含まれない。

## Changed Files

| File | Change |
|------|--------|
| agent/ionos_rules.py | **差分なし** (main と同一) |
| submission.tar.gz | **差分なし** |
| reports/level5_f0010_conditional_voltorb_pivot.md | 新規（検証記録） |
| reports/level5_f0010_conditional_voltorb_pivot.json | 新規 |
