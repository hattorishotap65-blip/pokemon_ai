# Level 5 A/B Test Report: F0003

## Target

F0003: bellibolt_over_voltorb_high_damage

## Fix Applied

**File:** `agent/ionos_rules.py` Rule 17b (RETREAT)

Bellibolt ex がアクティブで攻撃可能（4+エネ）でも、ベンチの Voltorb が攻撃可能（2+エネ）かつ推定打点 >= 240（Bellibolt ex の固定 230 を上回る）場合、retreat suppression を解除（-700 → +80）。

### なぜこの修正にしたか

- F0001/F0002 と同じ retreat override パターンで一貫性を保つ
- 閾値 240 は Bellibolt ex の固定 230 を明確に上回る場合のみ発火するため、安全
- Bellibolt でしかKOできないケースは 230 > Voltorb推定打点 で従来通り Bellibolt を維持

## A/B Test Results (50g vs 50g)

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| anomalies_total | 5.62/g | 4.54/g | **-1.08** |
| **bellibolt_over_voltorb_high_damage** | **1.72/g** | **0.74/g** | **-0.98 (-57%)** |
| voltorb_over_kilowattrel_missed | 1.44/g | 1.22/g | -0.22 |
| voltorb_over_wattrel_missed | 0.12/g | 0.02/g | -0.10 |
| bellibolt_attack_probably_correct | 2.34/g | 2.54/g | +0.20 |
| attack_available_but_no_attack | 0.00/g | 0.00/g | **0** |
| end_when_attack_available | 0.00/g | 0.00/g | **0** |
| retreat_when_attack_available | 0.00/g | 0.00/g | **0** |
| **Fix trigger count** | — | **175 times (3.5/g)** | — |

## Decision

**accept**

## Reasons

1. F0003 が **86 → 37 件に減少（-57%）**
2. 修正コードが **175 回発火（3.5/game）** — 実際に挙動が変わっている
3. 全異常合計が **281 → 227（-19%）**
4. **安全指標すべて 0 のまま**（end/retreat/attack_available_but_no_attack）
5. F0001/F0002 の改善も維持（wattrel 0.12→0.02, kilowattrel 1.44→1.22）
6. `compare_anomaly_reports.py` の判定: **accept**
7. bellibolt_attack_probably_correct が +0.20/g 増加 — Bellibolt 攻撃が妥当なケースの割合が相対的に増えただけで問題なし

## Safety Check

| Check | Result |
|-------|--------|
| error_rate | 0% (unchanged) |
| end_when_attack_available | 0 (unchanged) |
| retreat_when_attack_available | 0 (unchanged) |
| attack_available_but_no_attack | 0 (unchanged) |
| deck.csv | 未変更 |
| PDF | 未追加 |
| submission.tar.gz | 再生成済み |

## Next Recommended Action

F0003 は accept。残りの anomaly 内訳：
- bellibolt_attack_probably_correct: 127件 — **修正不要**
- voltorb_over_kilowattrel_missed: 61件 — retreat アプローチの限界（F0002 と同様）
- bellibolt_over_voltorb_high_damage: 37件 — 閾値調整（240→230等）で追加改善可能だが、リスクと効果を評価すべき
