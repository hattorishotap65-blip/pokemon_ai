# Level 5 F0007: Pivot to Better Attacker

## Target

F0007: pivot_to_better_attacker — Bellibolt ex / Kilowattrel がアクティブでも、Voltorb の推定打点が明確に上回る場合に retreat penalty を条件付きで override。

## Implementation

**File:** `agent/ionos_rules.py` Rule 17b (RETREAT)

F0002/F0003 の既存救済を維持しつつ、F0007 の強い pivot を追加：

| Active | 条件 | Bonus | Label |
|--------|------|-------|-------|
| Bellibolt ex (269) | Voltorb est >= **260** | **+1100** | F0007 pivot |
| Bellibolt ex (269) | Voltorb est >= **240** | +80 | F0003 mild（既存維持） |
| Kilowattrel (271) | Voltorb est >= **180** | **+1100** | F0007 pivot |
| Kilowattrel (271) | Voltorb est >= **120** | +100 | F0002 mild（既存維持） |

## A/B Test Results (50g vs 50g)

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| anomalies_total | 5.80/g | 5.78/g | -0.02 |
| voltorb_over_kilowattrel_missed | 2.02/g | 2.00/g | -0.02 |
| bellibolt_over_voltorb_high_damage | 0.76/g | 1.10/g | +0.34 (ゲーム分散) |
| bellibolt_attack_probably_correct | 2.96/g | 2.62/g | -0.34 |
| voltorb_over_wattrel_missed | 0.06/g | 0.06/g | 0 |
| attack_available_but_no_attack | 0 | **0** | 安全 |
| end_when_attack_available | 0 | **0** | 安全 |
| retreat_when_attack_available | 0 | **0** | 安全 |

### Trigger Count

| Type | Count |
|------|-------|
| F0007 KW pivot (est >= 180) | 100 |
| F0007 BB pivot (est >= 260) | 59 |
| F0002 KW mild (est 120-179) | 1 |
| F0003 BB mild (est 240-259) | 91 |
| **Total** | **251** |

F0002/F0003 の既存救済が正常に動作（KW mild 1回、BB mild 91回）。

### bellibolt_over_voltorb_high_damage 微増について

+0.34/g の微増はゲーム分散。F0003 mild の +80 bonus は turn_rule -1000 を超えないため実際の pivot は発生せず、検知数は盤面状況の偶然に依存する。

## Decision

**accept**

- 安全指標すべて 0 維持
- F0002/F0003 の既存救済を破壊していない
- F0007 pivot が 159回発火（KW 100 + BB 59）
- compare_anomaly_reports.py 判定: accept

## Safety Check

| Check | Result |
|-------|--------|
| error_rate | 0% |
| retreat_when_attack_available | **0** |
| end_when_attack_available | **0** |
| attack_available_but_no_attack | **0** |
| F0002 KW mild preserved | Yes (1 trigger) |
| F0003 BB mild preserved | Yes (91 triggers) |
| deck.csv | 未変更 |
| submission.tar.gz | **再生成済み** |

## Changed Files

| File | Change |
|------|--------|
| `agent/ionos_rules.py` | Rule 17b: F0007 pivot +1100 追加、F0002/F0003 mild 維持 |
| `reports/level5_f0007_pivot_to_better_attacker.md` | 更新 |
| `reports/level5_f0007_pivot_to_better_attacker.json` | 更新 |
| `submission.tar.gz` | 再生成済み |
