# Claude Code Instruction: Voltorb Scaling Win Condition Correction

## Purpose

Correct the strategic interpretation of the Iono's Lightning deck.

The previous simplified win condition over-emphasized attacking with Iono's Bellibolt ex / Iono's Kilowattrel after evolution. The corrected win condition is Voltorb-centered:

```text
Use Iono's Bellibolt ex as an energy acceleration engine.
Spread Basic Lightning Energy across Iono's Pokemon.
Use the total Lightning Energy on all own Iono's Pokemon to increase Iono's Voltorb damage.
Attack primarily with Iono's Voltorb when its expected damage is strong enough.
Use Bellibolt ex / Kilowattrel as backup attackers or closers.
```

This correction should supersede any fixed attacker ranking such as:

```text
Bellibolt ex > Kilowattrel > Voltorb > Wattrel > Tadbulb
```

That fixed ranking is misleading because Voltorb's damage is dynamic and depends on total Lightning Energy attached to all own Iono's Pokemon.

---

## Correct Win Condition

### Primary plan

```text
1. Develop multiple Basic Iono's Pokemon.
2. Get Iono's Voltorb to 2 Energy so it can attack.
3. Evolve Tadbulb into Iono's Bellibolt ex.
4. Use Bellibolt ex's Ability to attach Basic Lightning Energy from hand to any Iono's Pokemon.
5. Spread Lightning Energy across the board to increase Voltorb's damage.
6. Attack with Voltorb when its estimated damage is enough for meaningful pressure or KO.
7. Use Bellibolt ex / Kilowattrel only when they are the best damage / KO / prize-race option.
8. Use Energy Retrieval / Night Stretcher / Max Rod / Levincia to keep Energy and attackers flowing.
```

### Why Voltorb is central

Iono's Voltorb's attack scales with the total number of Lightning Energy attached to all own Iono's Pokemon.

Expected formula:

```text
Voltorb damage = 20 + 20 * total_basic_lightning_energy_attached_to_own_iono_pokemon
```

This means Energy on Bellibolt ex / Tadbulb / Wattrel / Kilowattrel can still increase Voltorb's attack damage.

Voltorb is also non-ex, so it is more prize-efficient than Bellibolt ex when its damage is comparable.

---

## Correct Role Assignment

### Iono's Voltorb

```text
Primary attacker
Non-ex scaling attacker
Prize-efficient pressure source
Needs 2 Energy to attack
Damage increases from Lightning Energy on all own Iono's Pokemon
```

### Iono's Bellibolt ex

```text
Primary energy engine
Backup / closer attacker
2-prize liability if overused as the default attacker
Its Ability should often be valued more than its attack
```

### Iono's Kilowattrel

```text
Backup non-ex attacker
Draw support
Useful follow-up attacker, but not the primary win condition
```

### Iono's Wattrel / Tadbulb

```text
Evolution bases
Energy spread targets for Voltorb scaling
Usually not preferred attackers unless no better legal attack exists
```

---

## Strategic Correction to Previous 10-Game Review

The previous 10-game review focused on this concept:

```text
stronger_ready_bench_attacker_not_promoted
```

That is still useful, but it must not mean:

```text
Always pivot to Bellibolt ex when Bellibolt ex is ready.
```

Correct interpretation:

```text
Choose the best attacker by expected damage, KO potential, prize efficiency, and future risk.
```

So the more accurate anomaly types are:

```text
voltorb_scaling_attack_underused
best_damage_attacker_not_selected
bellibolt_attack_overpreferred_when_voltorb_damage_is_sufficient
weak_active_attack_chosen_over_voltorb_scaling_attack
```

`stronger_ready_bench_attacker_not_promoted` should remain generic, but it should use dynamic expected damage. It should not use a fixed priority table where Bellibolt ex always outranks Voltorb.

---

## Files Updated by This PR

This PR updates strategic data files so future scoring and analysis can use the corrected model:

```text
data/deck_profile.json
data/card_effects_iono_lightning_recommended_en_ja.json
docs/instructions/20260619_voltorb_scaling_win_condition_correction.md
```

The profile changes are intended to guide future Claude Code implementation. They do not by themselves change battle behavior unless the agent already consumes those profile fields.

---

## Required Implementation Direction

When implementing behavior changes later, Claude Code should do the following:

```text
1. Estimate Voltorb damage every time an attack option is evaluated.
2. Count Basic Lightning Energy attached to all own Iono's Pokemon.
3. Compare Voltorb expected damage against Bellibolt ex / Kilowattrel fixed damage.
4. Include prize efficiency: Voltorb is non-ex, Bellibolt ex gives up 2 prizes.
5. Prefer Voltorb when its expected damage is sufficient.
6. Use Bellibolt ex attack when 230 damage is needed or Voltorb is unavailable.
7. Use Kilowattrel as backup or when it is the best legal non-ex attacker.
```

---

## Detection Updates Needed

### New anomaly: voltorb_scaling_attack_underused

Detect when:

```text
- Voltorb has at least 2 Energy
- Voltorb has legal Attack or can become Active legally
- Total Lightning Energy on own Iono's Pokemon makes Voltorb damage high enough
- Agent chooses a lower-value attack instead
```

Example output:

```json
{
  "type": "voltorb_scaling_attack_underused",
  "severity": "medium",
  "active_id": 270,
  "bench_candidate_id": 265,
  "voltorb_energy_count": 2,
  "total_iono_lightning_energy": 8,
  "estimated_voltorb_damage": 180,
  "actual_action": "attack_with_lower_damage_attacker",
  "expected_action": "consider_voltorb_scaling_attack",
  "suggested_fix_area": [
    "strategy_engine.estimate_attack_damage",
    "strategy_engine.score_attack_option",
    "data/deck_profile.json damage_model"
  ]
}
```

### New anomaly: bellibolt_attack_overpreferred_when_voltorb_damage_is_sufficient

Detect when:

```text
- Bellibolt ex attacks
- Voltorb could attack or could be promoted to attack
- Voltorb estimated damage is enough for the same KO or meaningful pressure
- Bellibolt ex attack exposes a 2-prize Pokemon without clear benefit
```

### New anomaly: best_damage_attacker_not_selected

Generic version:

```text
- Multiple legal attacks or reachable attacks exist
- One candidate has clearly better expected damage / KO value / prize efficiency
- Agent selected a weaker attacker
```

---

## Scoring Updates Needed Later

Do not implement behavior changes in this documentation PR. For a later implementation PR, use this scoring direction:

```text
score_attack_option =
    legal_action_score
  + estimated_damage_score
  + ko_bonus
  + prize_efficiency_bonus
  + role_bonus
  - overexposure_penalty
  - next_turn_lock_penalty
```

Voltorb-specific scoring:

```text
estimated_voltorb_damage = 20 + 20 * total_iono_lightning_energy

if voltorb_can_attack:
    score += estimated_voltorb_damage_bonus
    if estimated_voltorb_damage >= useful_threshold:
        score += voltorb_scaling_bonus
    if estimated_voltorb_damage >= opponent_active_hp:
        score += ko_bonus
    if competing_attacker_is_ex and Voltorb reaches similar damage:
        score += prize_efficiency_bonus
```

Bellibolt-specific scoring:

```text
if Bellibolt ex attack reaches KO and Voltorb does not:
    attack_score += bellibolt_ko_bonus
else if Voltorb reaches comparable damage:
    Bellibolt attack should not automatically outrank Voltorb

Ability should stay very high because it enables Voltorb damage scaling.
```

---

## Do Not Do

Do not:

```text
- make Bellibolt ex the default main attacker
- use a fixed attacker priority ranking that always puts Bellibolt ex over Voltorb
- treat Kilowattrel as the primary win condition
- weaken the existing rule that prevents End when Attack is available
- change deck.csv
- rebuild submission unless explicitly requested
- auto-merge behavior changes without A/B comparison
```

---

## Claude Code Prompt: Detection Phase

Use this prompt after merging this PR.

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Voltorb scaling win-condition detection

## 必ず読むファイル

- CLAUDE.md
- docs/instructions/20260619_battle_log_diagnostic_pipeline.md
- docs/instructions/20260619_pdca_self_learning_loop.md
- docs/instructions/20260619_10game_battle_log_review_retreat_priority.md
- docs/instructions/20260619_voltorb_scaling_win_condition_correction.md
- data/deck_profile.json
- data/card_effects_iono_lightning_recommended_en_ja.json

## 目的

Iono's Lightningの勝ち筋をVoltorb scaling中心として扱い、以下の検知ができるようにしてください。

- voltorb_scaling_attack_underused
- best_damage_attacker_not_selected
- bellibolt_attack_overpreferred_when_voltorb_damage_is_sufficient

## 実装すること

1. 自分のIono's Pokemon全体についているBasic Lightning Energy数を推定する関数を追加する
2. Voltorbの推定ダメージを計算する
   - damage = 20 + 20 * total_iono_lightning_energy
3. 攻撃候補ごとの推定ダメージを比較する
4. Voltorbが2エネ以上で攻撃可能な場合、Voltorb攻撃を高評価する検知ロジックを追加する
5. Bellibolt ex攻撃がVoltorbより常に優先されないよう、レポート上で検知できるようにする
6. reports/latest_anomaly_report.json / md / summary に出せるようにする

## 今回やらないこと

- policy.py の行動変更
- strategy score の本格変更
- deck.csv の変更
- submission.tar.gz の再ビルド
- 自動修正
- 自動merge

## 完了条件

- Voltorb推定ダメージがレポートに出せる
- Voltorbの攻撃可能状態を検知できる
- Bellibolt ex / Kilowattrel / Voltorb の固定優先度ではなく、推定打点で比較できる
- 既存の attack_available_but_no_attack / end_when_attack_available 検知を壊していない
- 変更ファイルと実行コマンドを報告する
```

---

## Claude Code Prompt: Behavior Phase

Detection confirmed after the detection phase, use this prompt.

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Voltorb scaling attack scoring

## 目的

Voltorbが2エネ以上で攻撃可能かつ盤面のIono's Pokemon全体の雷エネルギー数により十分な打点が出る場合、Bellibolt ex / KilowattrelよりVoltorb攻撃を適切に高評価する。

## 実装方針

- select.option を合法手の正とする
- Voltorb damage = 20 + 20 * total_iono_lightning_energy
- Bellibolt ex AbilityはVoltorb打点を伸ばすために引き続き高評価
- Bellibolt ex攻撃は230点が必要な場面では高評価
- Voltorbで同等以上の価値があるなら、非exのVoltorbを優先
- Activeが弱いWattrel/Tadbulbで、Benchに攻撃可能VoltorbがいるならPivot/Retreatを検討

## 今回やらないこと

- deck.csv変更
- 大規模リファクタ
- unrelated cleanup
- 自動merge

## 完了条件

- Voltorb攻撃回数と勝率をA/B比較できる
- bellibolt_attack_overpreferred_when_voltorb_damage_is_sufficient が減る
- attack_available_but_no_attack が増えない
- end_when_attack_available が増えない
- 50〜100戦以上で評価できる状態にする
```
