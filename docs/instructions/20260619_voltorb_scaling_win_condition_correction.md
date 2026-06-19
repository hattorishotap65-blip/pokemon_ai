# Claude Code Instruction: Voltorb Scaling Win Condition Correction

## Purpose

Correct the deck win condition and all related scoring / anomaly concepts for the Iono's Lightning deck.

This deck should not be treated as a simple Bellibolt ex / Kilowattrel evolution-attacker deck. The main win condition is to use Iono's Bellibolt ex as an energy acceleration engine, spread Lightning Energy across Iono's Pokemon, and attack with Iono's Voltorb as a high-damage non-ex scaling attacker.

---

## Correct Win Condition

The corrected win condition is:

```text
Deploy multiple Basic Iono's Pokemon
↓
Make Iono's Voltorb attack-ready with 2 Lightning Energy
↓
Evolve Iono's Tadbulb into Iono's Bellibolt ex
↓
Use Bellibolt ex's Ability to attach Lightning Energy from hand to Iono's Pokemon on board
↓
Increase total Lightning Energy attached to all own Iono's Pokemon
↓
Use Iono's Voltorb's scaling attack as the main non-ex prize-race attacker
↓
Use Bellibolt ex / Kilowattrel as engine, backup attackers, or finishers only when they are the best damage / KO option
↓
Recover energy and attackers with Energy Retrieval / Night Stretcher / Max Rod
```

---

## Incorrect Assumption to Avoid

Do not model the deck as:

```text
Evolve Bellibolt ex / Kilowattrel
↓
Attack primarily with Bellibolt ex / Kilowattrel
```

This misses the core synergy.

Bellibolt ex is not only an attacker. Its most important role is often:

```text
Energy acceleration engine for Voltorb's board-wide Lightning scaling damage.
```

---

## Role Correction

### Iono's Voltorb

Correct role:

```text
main_attacker
basic_attacker
scaling_attacker
non_ex_prize_race_attacker
```

Voltorb should be highly valued when:

```text
- it has 2 or more Lightning Energy and can attack
- total Lightning Energy on all own Iono's Pokemon is high
- its estimated damage can take KO or pressure prizes
- using Voltorb preserves prize efficiency compared with attacking using Bellibolt ex
```

Estimated damage concept:

```text
voltorb_damage = 20 + 20 * total_lightning_energy_attached_to_own_iono_pokemon
```

### Iono's Bellibolt ex

Correct role:

```text
energy_engine
stage1_ex_attacker
backup_attacker
finisher
```

Bellibolt ex should be highly valued when:

```text
- it can use Ability to increase total Lightning Energy on Iono's Pokemon
- it enables Voltorb scaling damage
- it can take a key KO that Voltorb cannot
- Voltorb is not available or not attack-ready
```

Do not always prefer Bellibolt ex over Voltorb just because Bellibolt ex has higher static attacker priority.

### Iono's Kilowattrel

Correct role:

```text
backup_attacker
non_ex_followup_attacker
draw_support
```

Kilowattrel is important, but it should not override a high-damage Voltorb attack when Voltorb is ready.

---

## Scoring Correction

Replace fixed attacker priority logic with expected value scoring.

Wrong:

```text
Bellibolt ex > Kilowattrel > Voltorb > Wattrel > Tadbulb
```

Correct:

```text
Best attacker = highest expected value considering:
- estimated damage
- KO possibility
- prize efficiency
- risk of giving up 2 prizes
- whether the attack advances the Voltorb scaling plan
```

Recommended default priority when damage is unknown:

```text
Voltorb ready with high board Lightning >= Bellibolt ex >= Kilowattrel > Voltorb not ready > Wattrel > Tadbulb
```

---

## Anomaly Concept Correction

Previous concept:

```text
stronger_ready_bench_attacker_not_promoted
```

This is too generic and may incorrectly push the agent toward Bellibolt ex even when Voltorb is the correct attacker.

Use these more accurate anomaly concepts instead:

```text
best_damage_attacker_not_selected
voltorb_scaling_attack_underused
bellibolt_engine_used_without_voltorb_payoff
```

---

## New Anomaly: voltorb_scaling_attack_underused

Detect when:

```text
- Iono's Voltorb is in Active or can be promoted legally
- Voltorb has at least 2 Lightning Energy, or can become attack-ready this turn
- total Lightning Energy on own Iono's Pokemon makes Voltorb damage high
- Voltorb attack is available or could be available through legal sequencing
- agent attacks with a lower-value attacker or spends the turn without using the Voltorb payoff
```

Suggested fields:

```json
{
  "type": "voltorb_scaling_attack_underused",
  "severity": "medium",
  "active_id": 265,
  "active_name": "Iono's Voltorb",
  "total_iono_lightning_energy": 6,
  "estimated_voltorb_damage": 140,
  "expected_action": "attack_with_voltorb_when_it_is_best_expected_damage",
  "actual_action": "used_lower_value_attack_or_setup_instead",
  "confidence": "medium",
  "suggested_fix_area": [
    "strategy_engine.score_attack_option",
    "ionos_rules.py Voltorb scaling damage",
    "data/deck_profile.json voltorb_scaling_policy"
  ]
}
```

---

## New Anomaly: best_damage_attacker_not_selected

Detect when:

```text
- Multiple legal attack options or legal promotion/pivot paths exist
- One attacker has clearly higher estimated damage or KO value
- The agent selects a weaker attack without obvious benefit
```

This should be generic enough to work across decks.

For Iono's Lightning, this detector must include Voltorb's board-wide Lightning scaling damage.

---

## Bellibolt ex Ability Evaluation

Bellibolt ex Ability should be evaluated by whether it improves the board state for Voltorb scaling, not only whether it makes Bellibolt ex attack-ready.

Good Ability use:

```text
- increases total Lightning Energy on Iono's Pokemon
- enables Voltorb to reach KO damage
- prepares another Iono's attacker while preserving Voltorb pressure
- creates a backup attacker without sacrificing current attack
```

Bad or lower-priority Ability use:

```text
- consumes the turn sequence but does not improve the current or next attack
- over-accelerates to a Pokemon that is already ready and not the intended attacker
- causes the agent to miss a stronger Voltorb attack line
```

---

## Energy Attachment Policy

For Voltorb scaling, Lightning Energy does not need to be stacked only on Voltorb after Voltorb reaches its attack requirement.

Correct policy:

```text
- First: make Voltorb attack-ready with 2 Lightning Energy
- Then: distribute Lightning Energy across own Iono's Pokemon to increase Voltorb damage while preparing backup attackers
- Prefer attachment that both increases Voltorb damage and improves future attacker readiness
```

Avoid:

```text
- treating extra Energy on Voltorb as always better than distributed Energy
- treating Bellibolt ex readiness as always more important than Voltorb scaling damage
```

---

## Files to Inspect / Update

Claude Code should inspect the current implementation and update only the files that actually contain these concepts.

Likely files:

```text
data/deck_profile.json
docs/ionos_kilowattrel_deck.md
docs/instructions/20260619_10game_battle_log_review_retreat_priority.md
agent/strategy_engine.py
agent/ionos_rules.py
agent/policy.py
tools/detect_anomalies.py
```

Do not change all files blindly.

---

## Safe Implementation Order

### Phase 1: Documentation and profile correction

Update deck profile / documentation so the core win condition is correct.

Expected:

```text
primary_win_condition emphasizes Voltorb scaling damage
main_attackers puts Voltorb first
Bellibolt ex is energy_engine + backup/finisher
Kilowattrel is backup attacker
late priorities include Voltorb scaling if damage is sufficient
```

### Phase 2: Detection only

Add anomaly detection for:

```text
voltorb_scaling_attack_underused
best_damage_attacker_not_selected
```

Do not change behavior yet.

### Phase 3: Behavior scoring

Only after detection works, adjust scoring so:

```text
- Voltorb's estimated damage is calculated
- Voltorb attack is strongly preferred when it is the best damage / prize-efficiency option
- Bellibolt ex Ability gets bonus when it increases Voltorb damage meaningfully
- Retreat/Pivot exception is based on best expected attacker, not fixed card priority
```

### Phase 4: A/B evaluation

Run 50-100 games and compare:

```text
- win rate
- Voltorb attack count
- estimated Voltorb damage at attack time
- best_damage_attacker_not_selected count
- voltorb_scaling_attack_underused count
- attack_available_but_no_attack count
- end_when_attack_available count
- retreat_when_attack_available count
```

---

## Do Not Do

```text
- Do not change deck.csv
- Do not assume Bellibolt ex is always the best attacker
- Do not assume Kilowattrel is always better than Voltorb
- Do not use fixed attacker priority without checking Voltorb estimated damage
- Do not make Retreat generally preferred over Attack
- Do not weaken the existing End/Retreat safety rules
- Do not auto-merge behavior changes
```

---

## Claude Code Prompt: Phase 1 Documentation/Profile Correction

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Voltorb scaling win condition correction: Phase 1 documentation/profile update

## 必ず読むファイル

- CLAUDE.md
- data/deck_profile.json
- docs/ionos_kilowattrel_deck.md
- docs/instructions/20260619_10game_battle_log_review_retreat_priority.md
- docs/instructions/20260619_voltorb_scaling_win_condition_correction.md

## 目的

Iono's Lightning の勝ち筋を正しく修正する。

正しい勝ち筋:
Bellibolt exで雷エネルギーを盤面のIono's Pokemonに展開し、盤面全体の雷エネルギー数でIono's Voltorbの火力を上げ、非exのVoltorbでサイド効率よく攻撃する。

## 修正すること

- `data/deck_profile.json` の win condition / priority / attacker role をVoltorb中心に修正
- `docs/ionos_kilowattrel_deck.md` の勝ち筋をVoltorb scaling中心に修正
- `docs/instructions/20260619_10game_battle_log_review_retreat_priority.md` の固定優先度表現を修正し、Bellibolt ex固定優先ではなく best expected damage / Voltorb scaling を使うようにする

## 今回やらないこと

- deck.csv の変更
- policy.py の変更
- agent本体のスコア変更
- anomaly detector の実装
- submission.tar.gz の再ビルド

## 完了条件

- Voltorb が main scaling attacker として明記されている
- Bellibolt ex が energy engine + backup/finisher として明記されている
- fixed priority `Bellibolt ex > Kilowattrel > Voltorb` が残っていない、または誤解を招かない形に修正されている
- deck.csv が変更されていない
- 変更ファイル一覧を報告する
```

---

## Claude Code Prompt: Phase 2 Detection

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Voltorb scaling win condition correction: Phase 2 detection only

## 目的

Voltorb scaling win condition に反する行動を検知できるようにする。

## 実装する anomaly

- `voltorb_scaling_attack_underused`
- `best_damage_attacker_not_selected`

## 実装方針

- Voltorb damage estimate = 20 + 20 * total Lightning Energy on own Iono's Pokemon
- Voltorbが2エネ以上で攻撃可能なら候補に入れる
- Bellibolt ex / Kilowattrel / Wattrel と固定優先度だけで比較しない
- KO可能性、推定打点、サイド効率を比較する

## 今回やらないこと

- policy.py の行動変更
- strategy scoring の本格変更
- deck.csv の変更
- submission.tar.gz の再ビルド

## 完了条件

- anomaly report に `voltorb_scaling_attack_underused` を出せる
- anomaly report に `best_damage_attacker_not_selected` を出せる
- 既存の missed attack / bad End / bad Retreat 検知を壊さない
```
