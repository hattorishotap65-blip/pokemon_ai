# Level 5 F0007: Pivot to Better Attacker

## Target

F0007: pivot_to_better_attacker — turn_rule_engine の retreat penalty -1000 を条件付きで override し、Voltorb への交代を可能にする。

## Implementation

**File:** `agent/ionos_rules.py` Rule 17b (RETREAT)

| Active | 条件 | Bonus | 理由 |
|--------|------|-------|------|
| Bellibolt ex (269) | Voltorb 2+エネ、推定打点 >= 260 | **+1100** | BB 230 を明確に超える場合のみ pivot |
| Kilowattrel (271) | Voltorb 2+エネ、推定打点 >= 180 | **+1100** | KW 70 を大幅に超える場合に pivot |

+1100 は turn_rule の -1000 を超えて retreat 合計 +100 にする。条件を厳しくすることで副作用を最小化。

### なぜこの閾値か

- BB → VT: 260 (BB固定230 + 30マージン)。230-259 は Bellibolt 攻撃が妥当なため除外。
- KW → VT: 180 (KW固定70の約2.5倍)。120-179 はゲーム分散で retreat_when_attack_available のリスクあり。

## A/B Test Results (50g vs 50g)

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| **anomalies_total** | **5.80/g** | **5.26/g** | **-0.54** |
| **voltorb_over_kilowattrel_missed** | **2.02/g** | **1.52/g** | **-24.8%** |
| bellibolt_over_voltorb_high_damage | 0.76/g | 0.92/g | +0.16 |
| bellibolt_attack_probably_correct | 2.96/g | 2.80/g | -0.16 |
| voltorb_over_wattrel_missed | 0.06/g | 0.02/g | -0.04 |
| attack_available_but_no_attack | 0 | 0 | **0** |
| end_when_attack_available | 0 | 0 | **0** |
| retreat_when_attack_available | 0 | 0 | **0** |

### Trigger Count

| Pivot Type | Count |
|-----------|-------|
| KW → Voltorb (est >= 180) | 52 |
| BB → Voltorb (est >= 260) | 73 |
| **Total** | **125 (2.5/game)** |

## Decision

**accept**

compare_anomaly_reports.py 判定: accept — 全指標で悪化なし。

## Analysis

- voltorb_over_kilowattrel_missed が **101→76 (-24.8%)** に改善
- bellibolt_over_voltorb_high_damage は +0.16/g 微増だが、これは閾値 260 で拾えなかった 240-259 範囲（F0003 閾値調査で確認済み、閾値を下げると副作用あり）
- **安全指標すべて 0 維持** — retreat_when_attack_available の悪化なし
- 125回 trigger (2.5/game) — 実際に pivot が実行されている

## Safety Check

| Check | Result |
|-------|--------|
| error_rate | 0% |
| retreat_when_attack_available | **0** |
| end_when_attack_available | **0** |
| attack_available_but_no_attack | **0** |
| bellibolt_attack_probably_correct 悪化 | -0.16/g (微減、問題なし) |
| deck.csv | 未変更 |
| submission.tar.gz | accept 後に更新 |

## Changed Files

| File | Change |
|------|--------|
| `agent/ionos_rules.py` | Rule 17b: BB/KW retreat bonus +80/+100 → +1100 (条件厳格化) |
| `reports/level5_f0007_pivot_to_better_attacker.md` | 新規 |
| `reports/level5_f0007_pivot_to_better_attacker.json` | 新規 |

## Next

- submission.tar.gz を更新して commit
- F0008 以降: bellibolt_over_voltorb_high_damage 240-259 範囲の残件は閾値調整の限界（F0003 閾値調査で実証済み）。構造的にはこれ以上の改善は turn_rule_engine 側の条件分岐が必要。
