# Claude Code Instruction: 10-Game Battle Log Review and Retreat Priority Fix

## Purpose

Analyze the first uploaded 10 battle logs and prepare a safe improvement plan for the Iono's Lightning agent.

This instruction is for Claude Code. Do not directly change battle policy until the requested phase is executed and validated.

---

## Input Logs Reviewed

The review was based on these 10 battle logs:

```text
80564539.json
80565171.json
80565672.json
80566138.json
80566770.json
80567273.json
80567740.json
80571244.json
80571821.json
80572276.json
```

All logs were valid `cabt` battle logs with DONE status.

Summary:

```text
Games reviewed: 10
Record: 5 wins / 5 losses
Selected attacks: 41
attack_available_but_no_attack: 0
end_when_attack_available: 0
retreat_when_attack_available: 0
possible_overattach_to_ready_attacker: 0
non_attack_selected_when_attack_available: 18
```

Selected attacks by attacker:

```text
Iono's Voltorb:      16
Iono's Kilowattrel:  10
Iono's Bellibolt ex: 10
Iono's Wattrel:       5
```

---

## Important Finding

The current agent is no longer showing the most obvious rules bug.

The following critical issues were **not** observed in this 10-game sample:

```text
- Attack option was available but the turn ended with no attack
- End was selected while Attack was available
- Retreat was selected while Attack was available as a simple mistaken retreat
- Clear over-attachment to an already-ready attacker
```

This means the previous attack-priority work is generally working.

However, the logs reveal a different strategic issue:

```text
The agent sometimes keeps attacking with a weak Active Pokemon even when a much stronger Bench attacker is already ready or can be made ready in the same turn.
```

The key example is game `80571821.json`.

---

## Representative Issue: Weak Active Attack vs Ready Bench Attacker

### Game

```text
80571821.json
Result: loss
Opponent: kurikuri54
Turn: 19
```

### Observed pattern

At turn 19, the agent had:

```text
Active:
- Iono's Wattrel
- 1 Lightning Energy
- legal Attack available
- legal Retreat available

Bench setup during the same turn:
- Iono's Bellibolt ex was evolved on Bench
- Bellibolt ex was accelerated from 0 to 4 Energy
- Bellibolt ex became a much stronger ready attacker
```

The agent then selected:

```text
Attack with Active Wattrel
```

instead of considering:

```text
Retreat / pivot into ready Bench Bellibolt ex, then attack with Bellibolt ex if legally possible
```

### Why this matters

The current rule often treats this pattern as correct because:

```text
Attack option exists -> attack is preferred over retreat
```

That is usually good, but it has an important exception:

```text
If Active attack is weak and a stronger Bench attacker is ready, Retreat may be the better play even though Active has a legal Attack.
```

---

## Secondary Finding: Setup Before Attack Is Concentrated in Losses

The detector found 18 cases where a non-attack action was selected while an attack option was already available.

These were not direct bugs because the same turn eventually attacked.

Distribution:

```text
Losses: 16 cases
Wins:    2 cases
```

Common examples:

```text
- Use Ability while Attack is already available, then attack later
- Attach Energy elsewhere while Attack is already available, then attack later
- Play setup cards while Attack is already available, then attack later
```

This is not automatically wrong, but it suggests that the agent may be spending too much action-selection priority on setup even after it has already reached a legal attack state.

---

## Strategic Problem to Fix

Do not weaken the existing rule that avoids End/Retreat mistakes too broadly.

Instead, add a narrow exception for stronger-ready-bench situations.

Current simplified behavior:

```text
if active_attack_available:
    strongly prefer attack
    strongly penalize retreat
```

Desired behavior:

```text
if active_attack_available:
    if bench has much stronger ready attacker and retreat/pivot is legal:
        consider retreat/pivot
    else:
        prefer attack and penalize retreat/end
```

---

## Recommended Fix Area

Likely files to inspect:

```text
agent/turn_rule_engine.py
agent/strategy_engine.py
agent/ionos_rules.py
agent/policy.py
data/deck_profile.json
```

Expected best location depends on current code structure:

```text
turn_rule_engine.py
  Keep universal rule classification here.
  Do not hardcode Iono-specific attacker rankings here.

strategy_engine.py or ionos_rules.py
  Add deck-aware evaluation for stronger-ready-bench attacker.

policy.py
  Integrate final score only if existing scoring path requires it.

data/deck_profile.json
  Add or use role / attacker priority / retreat policy if already available.
```

---

## Proposed Concept: stronger_ready_bench_attacker

Add a detector/scoring concept similar to:

```text
stronger_ready_bench_attacker
```

Definition:

```text
- Active has legal attack
- Active also has legal retreat or a legal switch/pivot action
- Bench contains an attacker that is ready to attack now
- Bench attacker has higher strategic priority than Active attacker
- Active attack does not appear to take KO or provide a clearly better outcome
```

If true:

```text
- Do not blindly penalize Retreat just because Active has Attack
- Give Retreat/Pivot a positive or neutral score
- Give weak Active attack a relative penalty
```

---

## Suggested Attacker Priority for Iono's Lightning

For this deck, a rough attacker priority is:

```text
Bellibolt ex  >  Kilowattrel  >  Voltorb  >  Wattrel  >  Tadbulb
```

Suggested profile-style data:

```json
{
  "attacker_priority": {
    "269": 100,
    "271": 80,
    "265": 50,
    "270": 20,
    "268": 5
  },
  "retreat_policy": {
    "allow_retreat_when_attack_available_if_bench_attacker_priority_delta_at_least": 40,
    "avoid_retreat_if_active_attack_can_take_ko": true
  }
}
```

Do not hardcode this ranking inside the generic rule layer if a profile-driven mechanism exists.

---

## MVP Phase 1: Add Detection Only

Before changing behavior, add or extend anomaly detection so future logs can explicitly flag this pattern.

### Add anomaly type

```text
stronger_ready_bench_attacker_not_promoted
```

### Detect when

```text
- Active has legal Attack
- Active has legal Retreat or a legal switching/pivot option
- Active attacker priority is lower than at least one Bench ready attacker
- Agent chooses Active attack instead of retreat/pivot
```

### Output fields

```json
{
  "type": "stronger_ready_bench_attacker_not_promoted",
  "severity": "medium",
  "active_id": 270,
  "active_name": "Iono's Wattrel",
  "active_energy_count": 1,
  "bench_candidate_id": 269,
  "bench_candidate_name": "Iono's Bellibolt ex",
  "bench_candidate_energy_count": 4,
  "expected_action": "consider_retreat_or_pivot_to_stronger_attacker",
  "actual_action": "attack_with_weaker_active",
  "confidence": "medium",
  "suggested_fix_area": [
    "strategy_engine.score_retreat_option",
    "ionos_rules.py attacker priority",
    "data/deck_profile.json retreat_policy"
  ]
}
```

### Do not change behavior in MVP Phase 1

Detection-only is safer.

---

## MVP Phase 2: Behavior Change

After detection is visible and confirmed, implement scoring change.

### Behavior goal

When stronger ready Bench attacker exists, retreat/pivot should be considered even if Active has legal Attack.

### Scoring idea

```text
if active_attack_available and retreat_available:
    if stronger_ready_bench_attacker_exists:
        retreat_score += strong_bench_attacker_bonus
        active_attack_score -= weak_active_attack_penalty
    else:
        retreat_score -= avoid_retreat_when_attack_available_penalty
```

### Safety checks

Do not prefer retreat when:

```text
- Active attack can KO opponent active
- Bench attacker is not actually ready
- Retreat would leave no valid attacker active
- Switching/pivot action is not legal
- Retreat cost cannot be paid
```

---

## MVP Phase 3: A/B Evaluation

After behavior change, run before/after evaluation.

Minimum metrics:

```text
- win rate
- stronger_ready_bench_attacker_not_promoted count
- attack_available_but_no_attack count
- end_when_attack_available count
- retreat_when_attack_available count
- attacks by attacker
- average first meaningful attack turn
```

Acceptance criteria:

```text
- stronger_ready_bench_attacker_not_promoted decreases
- attack_available_but_no_attack remains 0 or does not increase materially
- end_when_attack_available remains 0
- retreat_when_attack_available does not increase due to bad retreats
- win rate does not worsen in at least 50-100 game sample
```

---

## Do Not Do

Do not:

```text
- change deck.csv
- weaken attack priority globally
- make Retreat generally preferred over Attack
- hardcode Iono-specific card IDs into generic rule engine if profile data exists
- accept changes without A/B comparison
- rebuild submission unless explicitly requested
```

---

## Claude Code Prompt: MVP Phase 1 Detection

Use this prompt to implement only the detection piece.

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

10-game battle log review: stronger-ready-bench attacker detection

## 必ず読むファイル

- CLAUDE.md
- docs/instructions/20260619_battle_log_diagnostic_pipeline.md
- docs/instructions/20260619_pdca_self_learning_loop.md
- docs/instructions/20260619_10game_battle_log_review_retreat_priority.md
- data/deck_profile.json

## 目的

戦歴ログ分析で見つかった以下のパターンを検知できるようにする。

Activeに合法Attackがあるが、Benchにより強いready attackerが存在し、Retreat/Pivotも合法なのに、弱いActiveで攻撃している。

代表例:
- 80571821.json
- turn 19
- Active: Iono's Wattrel, 1 Energy, Attack available, Retreat available
- Bench: Iono's Bellibolt ex, 4 Energy, stronger ready attacker
- Actual: Attack with Wattrel
- Expected: consider retreat/pivot into Bellibolt ex if legal

## 実装すること

- anomaly type `stronger_ready_bench_attacker_not_promoted` を追加する
- Active attacker priority と Bench attacker priority を比較できるようにする
- deck_profile に attacker_priority / retreat_policy があれば使う
- ない場合は安全なデフォルトか unknown として扱う
- reports/latest_anomaly_report.json に出力できるようにする
- reports/latest_anomaly_report.md / summary にも出す

## 今回やらないこと

- 行動ロジック変更
- policy.py の大幅変更
- deck.csv の変更
- strategy score の本格変更
- 自動修正
- 自動merge

## 守ること

- Attack option がある時に End/Retreatを避ける既存ルールは壊さない
- ただし、将来の挙動変更で使えるように、この例外パターンを検知可能にする
- 汎用ルール層にIono専用の固定値を入れすぎない

## 完了条件

- `stronger_ready_bench_attacker_not_promoted` が anomaly report に出せる
- サンプルログ 80571821 の turn 19 相当を検知できる
- 既存の `attack_available_but_no_attack` / `end_when_attack_available` / `retreat_when_attack_available` の検知を壊していない
- deck.csv は変更されていない
- 変更ファイルと実行コマンドを報告する
```

---

## Claude Code Prompt: MVP Phase 2 Behavior Change

Detection confirmed after Phase 1, use this prompt.

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Retreat/Pivot exception for stronger ready Bench attacker

## 目的

Activeに合法Attackがある場合でも、Benchに明らかに強いready attackerがいてRetreat/Pivotが合法なら、弱いActive攻撃よりRetreat/Pivotを検討できるようにする。

## 実装方針

- 既存の「Attack availableならEnd/Retreatを強く避ける」ルールを完全には消さない
- `stronger_ready_bench_attacker` の場合だけ例外を設ける
- Active attackがKOを取れる可能性がある場合はAttack優先を維持する
- Bench attackerがreadyでない場合は例外にしない

## 今回やらないこと

- deck.csv変更
- 大規模リファクタ
- 自動merge
- unrelated cleanup

## 完了条件

- 80571821 turn 19 のような局面で、Retreat/Pivot候補が強く評価される
- Attack available but no attack の悪化がない
- 50-100戦でA/B比較できる状態にする
```
