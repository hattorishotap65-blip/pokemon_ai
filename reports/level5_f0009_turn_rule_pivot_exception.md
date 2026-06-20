# F0009: Turn Rule Pivot Exception — Not Adopted

## Final Decision

**not_adopted** — F0009 は agent behavior に反映しない。検証記録として残す。

## What Was Tested

F0002/F0003 の mild retreat bonus (+80/+100) を +1100 に引き上げ、turn_rule -1000 を超えて pivot 可能にする試み。

## Results

### F0009 Full (BB+KW) — 200g vs 200g

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| bellibolt_over_voltorb_high_damage | 0.67/g | 0.82/g | **+22% worsened** |
| voltorb_over_wattrel_missed | 0.15/g | 0.34/g | **+127% worsened** |

**Rejected.** BB 240-259 の打点差 (max 29) が retreat cost に見合わない。

### F0009 KW-Only — 200g vs 200g

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| voltorb_over_kilowattrel_missed | 1.42/g | 1.55/g | **+0.14 worsened** |
| F0009 KW triggers | — | 36 (0.18/g) | low |

**Rejected.** 改善ターゲットの voltorb_over_kilowattrel_missed が悪化。trigger 頻度も低い。

## Why Not Adopted

1. F0009 full: BB 240-259 の強制 pivot が下流の anomaly を悪化
2. F0009 KW-only: trigger 36回/200g と低頻度、KW missed が改善せず悪化
3. Safety は all 0 だが、改善条件（KW missed 減少）を満たさない
4. 一律 +1100 bonus は条件が粗すぎる

## Current State

agent/ionos_rules.py は **F0007/F0008 相当に復元済み**。F0009 の behavior change は含まれない。

## Lessons Learned

- mild 範囲 (BB 240-259, KW 120-179) は打点差が小さく、一律 pivot のメリットが限定的
- 次の改善は「一律ボーナス」ではなく、条件付き（Voltorb 即攻撃可能 + サイド効率 + 被KOリスク）で設計すべき

## Changed Files (this PR)

| File | Change |
|------|--------|
| agent/ionos_rules.py | **差分なし** (main と同一に復元) |
| submission.tar.gz | **差分なし** (main と同一) |
| reports/level5_f0009_turn_rule_pivot_exception.md | 検証記録 |
| reports/level5_f0009_turn_rule_pivot_exception.json | 検証記録 |
