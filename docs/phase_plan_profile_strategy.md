# Phase-based Development Rules for Claude Code

このドキュメントは、Claude Code に読み込ませるための開発ルールです。  
目的は、profile-driven strategy 導入作業を一気に進めず、フェーズ単位で安全に実装することです。

---

## 1. 基本方針

このプロジェクトは、必ずフェーズ単位で進めます。

Claude Code は、ユーザーから明示されたフェーズだけを実施してください。  
指定されていないフェーズには進まないでください。

---

## 2. CLAUDE.md に記載する推奨内容

`CLAUDE.md` には、常時守るルールだけを短く記載します。  
詳細なフェーズ計画は、このドキュメント、または `docs/phase_plan_profile_strategy.md` に分けて管理します。

推奨記載例:

```md
## Development Process Rules

This project must be developed phase by phase.

Do not implement multiple phases at once.

Before starting any phase, read the relevant phase document.

Current phase plan:
- docs/phase_plan_profile_strategy.md

Rules:
- Only work on the phase explicitly requested by the user.
- Do not proceed to the next phase without user approval.
- Do not perform unrelated refactoring.
- Do not change `deck.csv` unless explicitly instructed.
- Do not modify the submission package structure unless explicitly instructed.
- If a requested change affects multiple phases, stop and explain the dependency before editing.
- At the end of each phase, report:
  - changed files
  - reason for each change
  - verification results
  - remaining issues
  - whether it is safe to proceed to the next phase

Important:
- `CLAUDE.md` contains always-on coding rules.
- Detailed phase instructions are maintained in `docs/phase_plan_profile_strategy.md`.
- Deck-specific strategy should be written in profile files such as `data/iono_deck_profile_v2.json`, not hardcoded directly into `policy.py`.
```

---

## 3. 推奨ディレクトリ構成

```text
project-root/
  CLAUDE.md
  docs/
    coding_rules.md
    phase_plan_profile_strategy.md
  data/
    iono_deck_knowledge_enhanced.md
    iono_deck_profile_v2.json
  prompts/
    phase_00_current_analysis.md
    phase_01_profile_load.md
    phase_02_strategy_engine_skeleton.md
```

役割:

```text
CLAUDE.md
  常時守るルールのみを書く

docs/phase_plan_profile_strategy.md
  フェーズ一覧・完了条件・禁止事項を書く

data/iono_deck_knowledge_enhanced.md
  人間向けのデッキ仕様書

data/iono_deck_profile_v2.json
  strategy_engine が読む機械可読のデッキ方針

prompts/phase_xx_*.md
  Claude Code に実行させるフェーズ別プロンプト
```

---

## 4. 全フェーズ共通ルール

すべてのフェーズで以下を守ってください。

```text
- deck.csv は変更しない
- 既存の提出構成を壊さない
- simulator の select.option を合法手の正とする
- type=10 は Ability
- type=12 は Retreat
- type=13 + attackId のみ Attack
- type=14 は End
- type=12 を攻撃扱いしない
- Ability はターン終了扱いしない
- Attack と End はターン終了行動として扱う
- Attack option がある場合、End / Retreat は強く減点する
- カード効果は effect_engine.py に置く
- ポケカ共通ルールは turn_rule_engine.py に置く
- デッキ方針は deck_profile_v2.json / strategy_engine.py に置く
- 最終選択は policy.py で行う
- 不要なリファクタリングはしない
- 指示されたフェーズ以外に進まない
```

---

# Profile-driven Strategy Phase Plan

## Purpose

デッキ固有の戦略を Python に直書きするのではなく、profile-driven な構成に移行する。

目的:

```text
デッキ固有コードを書く
↓
デッキ固有データを書く
↓
汎用 strategy_engine.py が deck_profile_v2.json を読んで評価する
```

主な対象ファイル:

```text
data/iono_deck_knowledge_enhanced.md
data/iono_deck_profile_v2.json
agent/strategy_engine.py
agent/policy.py
agent/ionos_rules.py
agent/effect_engine.py
agent/turn_rule_engine.py
```

---

## Phase 0: Current State Analysis

### Goal

現在のコード構成を確認し、profile-driven strategy 導入の実装計画を作る。

### Allowed changes

なし。  
このフェーズではコード変更・ファイル作成・削除をしない。

### Check targets

```text
agent/policy.py
agent/ionos_rules.py
agent/effect_engine.py
agent/turn_rule_engine.py
data/deck_profile.json
data/iono_deck_profile_v2.json
deck.csv
```

### Completion criteria

```text
- 現在のファイル構成が説明されている
- 既存の行動評価フローが説明されている
- strategy_engine.py を差し込む位置が明確
- 変更対象ファイルが列挙されている
- リスクが整理されている
- 次フェーズに進めるか判断できる
```

---

## Phase 1: Profile File Placement and Validation

### Goal

profile 関連ファイルを配置し、JSON形式を確認する。

### Allowed changes

```text
data/iono_deck_knowledge_enhanced.md
data/iono_deck_profile_v2.json
prompts/claude_code_prompt_profile_driven_strategy.md
```

Pythonコードは変更しない。

### Completion criteria

```text
- data/iono_deck_profile_v2.json が存在する
- JSONがパースできる
- deck.csv が変更されていない
- 提出構成が壊れていない
```

---

## Phase 2: Create strategy_engine.py Skeleton

### Goal

`agent/strategy_engine.py` の空枠を作る。

### Required functions

```python
load_deck_profile()
get_card_profile(card_id)
get_card_roles(card_id)
```

### Not allowed

```text
- policy.py にスコアを反映しない
- search / energy / ability / attack 評価はまだ実装しない
- 既存挙動を変えない
```

### Completion criteria

```text
- agent/strategy_engine.py が存在する
- import できる
- deck_profile_v2.json を読み込める
- card_id から roles を取得できる
```

---

## Phase 3: Missing Roles Detection

### Goal

profile を使って盤面の不足役割を判定する。

### Required function

```python
get_missing_roles(state)
```

### Missing roles

```text
need_voltorb
need_tadbulb
need_bellibolt
need_wattrel
need_kilowattrel
need_attacker
need_basic
need_evolution
```

### Not allowed

```text
- final_score に反映しない
- 行動選択を変えない
```

### Completion criteria

```text
- state から missing_roles を取得できる
- ログ出力できる
- 既存挙動は変わらない
```

---

## Phase 4: Strategy Preview Logging

### Goal

profile-driven 評価のプレビューをログに出す。  
この時点ではまだ final_score に加算しない。

### Required log fields

```text
deck_profile_id
card_roles
missing_roles
strategy_score_preview
strategy_reason_preview
profile_policy_used
```

### Not allowed

```text
- strategy score を final_score に加算しない
- 行動選択を変えない
```

### Completion criteria

```text
- シミュレーションログで profile 情報が見える
- 既存挙動が大きく変わらない
```

---

## Phase 5: Search Scoring

### Goal

検索対象の評価を profile-driven 化する。

### Targets

```text
Buddy-Buddy Poffin
Ultra Ball
Canari
```

### Required function

```python
score_search_target(card_id, state, search_source=None)
```

### Evaluation rules

```text
- missing_roles を埋めるカードを高評価
- 進化元が場にいる進化先を高評価
- 進化元がない Stage1 は低評価
- すでに手札にある Stage1 の重複取得は低評価
- Voltorb 不足時は Voltorb を評価
- Tadbulb 不足時は Tadbulb を評価
- Wattrel 不足時は Wattrel を評価
```

### Completion criteria

```text
- TadbulbなしでBellibolt exを取りすぎない
- WattrelなしでKilowattrelを取りすぎない
- Voltorb不足ならVoltorbを評価する
- duplicate Stage1 search が減る
```

---

## Phase 6: Energy Attach Scoring

### Goal

エネルギー添付評価を profile-driven 化する。

### Required function

```python
score_energy_attach_target(target, state, select=None, opponent_active=None)
```

### Evaluation rules

```text
- 攻撃可能化を最優先
- Voltorb 2エネ到達を高評価
- Kilowattrel 攻撃可能化を評価
- Bellibolt ex 攻撃可能化を評価
- Voltorb 本人への3枚目以降は低評価
- 他のIono’s Pokémonへの分散でVoltorb打点上昇を評価
- KOライン到達なら高評価
- 攻撃可能時の不要添付は低評価
```

### Completion criteria

```text
- Voltorb 1エネなら2枚目を高評価
- Voltorb 2エネ以上なら本人への追加添付を抑制
- 攻撃可能なら不要添付より攻撃優先
- Bellibolt ex Ability の添付先にも同じ基準を使う
```

---

## Phase 7: Ability Scoring

### Goal

Ability 評価を profile-driven 化する。

### Required function

```python
score_ability_option(opt, state, select=None)
```

### Bellibolt ex Ability

評価する条件:

```text
- 攻撃可能化
- Voltorb打点上昇
- KOライン到達
- 後続育成
```

抑制する条件:

```text
- すでに攻撃可能で、添付しても打点が変わらない
- 過剰添付になる
- 攻撃せずAbilityだけで終わりそう
```

### Kilowattrel Ability

評価する条件:

```text
- 手札1〜3枚
- 攻撃できるポケモンがいない
- Kilowattrelが攻撃可能でない
- 盤面が弱い
```

抑制する条件:

```text
- Kilowattrelが攻撃可能
- Abilityで攻撃可能状態が壊れる
- 手札5枚以上
- Attack option がある
```

### Completion criteria

```text
- Abilityをターン終了扱いしない
- Ability後にAttack optionがあれば攻撃する
- Kilowattrelが攻撃可能なのにAbilityでエネを捨てない
```

---

## Phase 8: Attack / End / Retreat Safety

### Goal

Attack / End / Retreat の安全評価を統合する。

### Required function

```python
score_attack_option(opt, state, select=None, opponent_active=None)
```

### Evaluation rules

```text
- Attack option があるなら Attack を高評価
- KOできる攻撃を最優先
- exをKOできる攻撃を高評価
- End when attack available は大減点
- Retreat when attack available は大減点
- type=12 は絶対に攻撃扱いしない
- type=13 + attackId のみ攻撃扱い
```

### Completion criteria

```text
- 攻撃可能なのにEndしない
- 攻撃可能なのにRetreatしない
- type=12 を攻撃扱いしない
- type=13 + attackId のみ攻撃扱い
```

---

## Phase 9: Discard and Recovery Scoring

### Goal

Ultra Ball コストや回収札の判断を profile-driven 化する。

### Required functions

```python
score_discard_candidate(card_id, state)
score_recovery_option(opt, state, select=None)
```

### Discard rules

捨てないカード:

```text
- 唯一のTadbulb
- 唯一のBellibolt ex
- 場にTadbulbがいる時のBellibolt ex
- 唯一のWattrel
- 場にWattrelがいる時のKilowattrel
- 後続不足時のVoltorb
- 手貼り用最後のBasic Lightning Energy
```

捨ててもよいカード:

```text
- 余剰Basic Lightning Energy
- 重複ポケモン
- 重複Levincia
- 有効対象のないPoké Pad
```

### Recovery rules

```text
- Recoveryは中盤以降に評価
- 次の攻撃役を優先
- 失ったメインエンジンを優先
- 進化元 + 進化先のセットを評価
- Energy Retrieval は手札エネ不足時に評価
```

### Completion criteria

```text
- 重要ラインを捨てない
- 余剰カードを優先して捨てる
- 回収札を序盤に無駄撃ちしない
```

---

## Phase 10: Cleanup and De-duplication

### Goal

`ionos_rules.py` に残る重複ロジックを整理する。

### Allowed changes

```text
- strategy_engine.py に委譲できる処理を委譲する
- 重複スコアを削減する
- 二重加点を防ぐ
```

### Not allowed

```text
- 動いているロジックを一気に削除しない
- profile-driven 側に同等ロジックがないものを削らない
- 挙動を大きく変える整理をしない
```

### Completion criteria

```text
- 重複スコアが減る
- 同じ評価が二重加点されない
- 既存挙動が維持または改善される
```

---

## Phase 11: Simulation and Weight Tuning

### Goal

シミュレーション結果を見て weight や profile を調整する。

### Metrics

```text
win_rate
attacks_per_game
turns_with_attack_available_but_no_attack
end_when_attack_available_count
retreat_when_attack_available_count
main_attacker_ready_turn
engine_ready_turn
bench_count_turn2
energy_in_play_turn3
duplicate_stage1_search_count
searched_stage1_without_base_count
overattach_to_ready_attacker_count
```

### Completion criteria

```text
- メトリクスが出力される
- 攻撃可能なのにEnd/Retreatする回数が減る
- 進化先だけ取りすぎる回数が減る
- Voltorb攻撃開始が早くなる
- Bellibolt ex 1体目が安定して立つ
- Kilowattrel Abilityの無駄撃ちが減る
```

---

# Claude Code Phase Execution Template

各フェーズを実行するときは、以下のテンプレートで指示してください。

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Phase X: <フェーズ名>

## 必ず読むファイル

- CLAUDE.md
- docs/phase_plan_profile_strategy.md
- data/iono_deck_knowledge_enhanced.md
- data/iono_deck_profile_v2.json

## 今回やること

<このフェーズでやること>

## 今回やらないこと

- 他フェーズの実装
- deck.csv の変更
- 不要なリファクタ
- 大規模な書き換え
- 提出構成の変更

## 守るルール

- simulator の select.option を合法手の正とする
- type=12 を攻撃扱いしない
- type=13 + attackId のみ攻撃扱いする
- Ability はターン終了扱いしない
- Attack option がある場合は End / Retreat を強く減点する
- カード効果は effect_engine.py
- デッキ方針は deck_profile_v2.json / strategy_engine.py
- 最終選択は policy.py

## 完了条件

<このフェーズの完了条件>

## 出力してほしい内容

- 変更ファイル一覧
- 変更理由
- 実装内容
- 確認結果
- 残課題
- 次フェーズに進めるか
```

---

# Recommended First Prompt

最初は Phase 0 だけ実施してください。

```md
次のフェーズだけ実施してください。
まだコード変更はしないでください。

## 対象フェーズ

Phase 0: Current State Analysis

## 必ず読むファイル

- CLAUDE.md
- docs/phase_plan_profile_strategy.md
- data/iono_deck_knowledge_enhanced.md
- data/iono_deck_profile_v2.json

## 今回やること

現在の提出コードを確認し、profile-driven strategy を導入するための実装計画を作成してください。

確認対象:
- agent/policy.py
- agent/ionos_rules.py
- agent/effect_engine.py
- agent/turn_rule_engine.py
- data/deck_profile.json
- data/iono_deck_profile_v2.json
- deck.csv

## 今回やらないこと

- コード変更
- ファイル作成
- deck.csv の変更
- 既存ロジック削除
- strategy_engine.py の作成

## 守るルール

- type=12 を攻撃扱いしない
- type=13 + attackId のみ攻撃扱いする
- Ability はターン終了扱いしない
- simulator の select.option を合法手の正とする
- deck.csv は変更しない

## 出力してほしい内容

1. 現在のファイル構成
2. 既存の行動評価の流れ
3. strategy_engine.py を入れるべき位置
4. deck_profile_v2.json を使える箇所
5. フェーズ別の実装計画
6. リスク
7. 最初に変更すべきファイル
8. Phase 1に進めるか
```
