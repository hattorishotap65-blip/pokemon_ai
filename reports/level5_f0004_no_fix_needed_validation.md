# F0004 No-Fix-Needed Validation Report

Generated: 2026-06-19 13:53 UTC

## Target

F0004: bellibolt_attack_probably_correct

## Summary

| Metric | Value |
|--------|-------|
| Games analyzed | 50 |
| F0004 count | 153 |
| F0003 count (for comparison) | 31 |
| Boundary leaks (F0004 with VT > 230) | 0 |

## F0003 / F0004 Boundary

| | F0003 | F0004 |
|---|---|---|
| Condition | actual=269 AND VT dmg > 230 | actual=269 AND VT dmg <= 230 |
| Actual damage range | 240+ | 120-220 |
| Gap | 221-239 (never occurs, damage is 20-step) |
| Boundary clean | YES |

## Voltorb Damage Distribution (F0004)

| Range | Count |
|-------|-------|
| 120-159 | 25 |
| 160-199 | 45 |
| 200-239 | 83 |

## Why No Fix Is Needed

1. **Bellibolt ex (230) >= Voltorb max (220)** in all 153 cases
2. 打点差は最大 10（230 vs 220）— retreat cost 3 を払う合理性なし
3. Retreat 後の 1 ターン loss + エネルギーロスで実質マイナス
4. サイド効率（非ex Voltorb が有利）を考慮しても、10 打点差では正当化できない
5. F0003 との境界リーク: **0件**

## Decision

**no_fix_needed**

- 分類条件は正しい
- Bellibolt ex 攻撃は全件で妥当
- detector / report 側の改善も不要
- agent 本体を変更していない

## Separate Issue Candidates

以下は F0004 とは別件。F0004 の修正対象には含めない。

| ID | Type | Severity | Game | Turn |
|---|---|---|---|---|
| A0001 | attack_available_but_no_attack | high | g1801 | 3 |
| A0002 | attack_available_but_no_attack | high | g1809 | 3 |

## Changed Files

| File | Change |
|------|--------|
| agent/ | **変更なし** |
| deck.csv | **変更なし** |
| submission.tar.gz | **変更なし** |
| reports/level5_f0004_no_fix_needed_validation.md | 新規作成 |
| reports/level5_f0004_no_fix_needed_validation.json | 新規作成 |
