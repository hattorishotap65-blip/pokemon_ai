# Claude Code Instruction: Battle Log Diagnostic Pipeline

## Purpose

戦歴ログから自動的に問題点を特定し、将来的に改善サイクルへつなげるための診断パイプラインを作成する。

この指示は Claude Code 向けです。  
最初から自動修正まで実装せず、まずは「検知・レポート化」だけを実装してください。

---

## Goal

現在は、人がバトルログを目視して以下のような問題を発見している。

```text
Bellibolt ex が攻撃すべきタイミングで攻撃していない
攻撃可能なのに End している
Ability を使った後に攻撃できるのに攻撃していない
進化元がない Stage1 を検索している
すでに攻撃可能なポケモンに過剰エネルギーを付けている
```

これらを自動検知できるようにする。

最終的に目指す流れ:

```text
battle_logs/inbox/
→ log normalization
→ turn tracking
→ anomaly detection
→ severity scoring
→ suggested fix area
→ JSON / Markdown report
→ LLM review packet
→ A/B evaluation
→ improvement decision
```

---

## Core Principle

まずは診断専用の仕組みを作る。

```text
Detect first.
Report second.
Review third.
Patch later.
A/B test before accepting.
```

このフェーズでは、AI本体の行動ロジックを変更しない。

---

## Required Directory Structure

以下を作成する。

```text
battle_logs/
  inbox/
    .gitkeep
  processed/
    .gitkeep
  ignored/
    .gitkeep

reports/
  anomaly_reports/
    .gitkeep
  latest_anomaly_report.json
  latest_anomaly_report.md
  latest_anomaly_summary.md

tools/
  analyze_battle_logs.py
  detect_anomalies.py
  generate_anomaly_report.py
```

役割:

```text
battle_logs/inbox/
  戦歴ログを投入する場所

battle_logs/processed/
  --move-processed 指定時に解析済みログを移動する場所

battle_logs/ignored/
  読み取れなかったログを移動する場所

reports/latest_anomaly_report.json
  機械可読の最新レポート

reports/latest_anomaly_report.md
  人間が読む最新レポート

reports/latest_anomaly_summary.md
  LLM / Claude Code / Codex に渡す短いレビュー用サマリ
```

---

## MVP Phase 1 Scope

### Create files

```text
tools/analyze_battle_logs.py
tools/detect_anomalies.py
tools/generate_anomaly_report.py
```

### CLI

以下で実行できるようにする。

```bash
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --move-processed
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --deck-profile data/deck_profile.json --top 20
```

### Input

最低限、以下を読み取れるようにする。

```text
.json
.jsonl
.log
```

ログ形式が完全に一致しなくても落ちにくくする。  
読めないファイルは ignored として記録する。

---

## Universal Option Type Rules

以下はデッキ非依存の固定ルール。

```text
type=10 -> Ability
type=12 -> Retreat
type=13 + attackId -> Attack
type=14 -> End
```

必ず守ること:

```text
- type=12 を Attack として扱わない
- type=13 かつ attackId がある場合のみ Attack
- Ability はターン終了扱いしない
- Attack と End はターン終了行動
- simulator の select.option を合法手の正とする
```

---

## Log Normalization

生ログを直接判定せず、まず共通イベント形式に正規化する。

正規化後の例:

```json
{
  "game_id": "unknown",
  "turn": 0,
  "player": 0,
  "phase": "select_action",
  "active_id": null,
  "active_name": null,
  "active_energy_count": null,
  "available_options": [],
  "selected_option": {},
  "selected_option_type": null,
  "selected_option_class": null,
  "has_legal_attack": false
}
```

欠損フィールドがあっても解析が落ちないようにする。

---

## Turn Tracking

同一ターン内の行動連鎖を追跡する。

重要:

```text
Ability を使った直後に攻撃していないだけでは異常と断定しない。
同一ターンの最後まで追跡し、最終的に Attack したかを確認する。
```

例:

```text
Attack optionあり
→ Ability
→ Energy attach
→ Attack
```

これは異常ではない。

```text
Attack optionあり
→ Ability
→ End
```

これは異常候補。

---

## Generic Anomaly Types

### attack_available_but_no_attack

条件:

```text
- 同一ターン中に Attack option が存在した
- そのターン中に Attack が選択されなかった
```

### end_when_attack_available

条件:

```text
- 現在の select.option に Attack option がある
- それにもかかわらず End を選択した
```

Severity: high

### retreat_when_attack_available

条件:

```text
- 現在の select.option に Attack option がある
- それにもかかわらず Retreat を選択した
```

Severity: high

### ability_without_followup_attack

条件:

```text
- Ability を使用した
- その前後で Attack option が存在した
- 同一ターン中に最終的に Attack しなかった
```

Ability後に最終的にAttackしている場合は検知しない。

### high_value_attack_not_used

条件:

```text
- legal Attack option が存在した
- active Pokémon が攻撃可能
- 高価値攻撃と思われる
- しかし攻撃しなかった
```

ダメージやKO情報が不足している場合は confidence を low / medium にする。

### ko_available_but_no_attack

条件:

```text
- 攻撃すれば相手ActiveをKOできそう
- しかし攻撃しなかった
```

正確なダメージ計算ができない場合は無理に検知しない。

### ability_breaks_attack_ready_state

条件:

```text
- draw_support などの Ability を使用
- 使用前は攻撃可能状態だった
- Abilityにより攻撃可能状態が壊れた可能性がある
```

deck_profile の role / ability_policy を使える場合は使う。

### overattach_to_ready_attacker

条件:

```text
- すでに攻撃可能なアタッカーにエネルギーを追加
- その添付が攻撃可能化 / KOライン到達 / 打点上昇 / 後続育成に寄与していない
```

avoid_overattach_after が deck_profile にあれば使う。

### stage1_without_base_search

条件:

```text
- Stage1 / evolution Pokémon を検索・取得
- 対応する evolves_from が場にいない
```

### duplicate_stage1_search

条件:

```text
- Stage1 / evolution Pokémon を検索・取得
- 同名カードがすでに手札にある
- deck_profile の search policy で重複回避が指定されている
```

### low_value_search

条件:

```text
- searchカードを使用
- 取得カードが missing_roles を埋めない
- 進化元なし / 同名過多 / 低価値理由がある
```

### discarded_protected_card

条件:

```text
- discard候補が deck_profile の discard policy で保護対象
```

例:

```text
only evolution base
only stage1 for base in play
last useful energy
only main attacker
```

---

## Deck Profile Awareness

Iono's Lightning 専用にしない。

カード名・カードIDの直書きは最小限にする。

使用する情報:

```text
roles
evolves_from
evolves_to
attack_energy_required
avoid_overattach_after
ability_policy
search policy
discard policy
recovery policy
```

role 例:

```text
main_attacker
sub_attacker
energy_engine
draw_support
evolution_base
stage1_attacker
search
recovery
```

デッキ固有の異常は、カード名ではなく role / policy で表現する。

---

## Severity

各 anomaly に severity を付ける。

```text
critical
high
medium
low
info
```

推奨:

```text
critical:
  KO available but no attack
  attack available but End selected
  protected win-condition card discarded

high:
  main attacker missed attack
  Retreat when attack available
  Ability breaks attack-ready state
  Stage1 searched without base

medium:
  overattach to ready attacker
  duplicate Stage1 search
  low-value search
  ability without follow-up attack

low:
  draw ability with large hand
  early recovery use
  weak setup inefficiency
```

---

## Suggested Fix Area

各 anomaly に、修正候補領域を含める。

例:

```json
{
  "suggested_fix_area": [
    "strategy_engine.score_attack_option",
    "strategy_engine.score_ability_option",
    "policy.py final_score integration",
    "data/deck_profile.json weights"
  ]
}
```

例:

```text
attack_available_but_no_attack:
  strategy_engine.score_attack_option
  policy.py final_score integration
  turn_rule_engine.py

ability_without_followup_attack:
  strategy_engine.score_ability_option
  policy.py action priority
  deck_profile ability_policy

overattach_to_ready_attacker:
  strategy_engine.score_energy_attach_target
  deck_profile energy policy

stage1_without_base_search:
  strategy_engine.score_search_target
  deck_profile search policy

discarded_protected_card:
  strategy_engine.score_discard_candidate
  deck_profile discard policy
```

---

## JSON Report

出力先:

```text
reports/latest_anomaly_report.json
```

構造:

```json
{
  "schema_version": "1.0",
  "deck_profile_id": "unknown",
  "source_dir": "battle_logs/inbox",
  "summary": {
    "files": 0,
    "games": 0,
    "turns": 0,
    "actions": 0,
    "anomalies_total": 0,
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "attack_available_but_no_attack": 0,
    "end_when_attack_available": 0,
    "retreat_when_attack_available": 0,
    "ability_without_followup_attack": 0,
    "overattach_to_ready_attacker": 0,
    "stage1_without_base_search": 0,
    "duplicate_stage1_search": 0
  },
  "anomalies": []
}
```

各 anomaly:

```json
{
  "id": "A0001",
  "severity": "high",
  "type": "attack_available_but_no_attack",
  "file": "sample.json",
  "game_id": "unknown",
  "turn": 4,
  "player": 0,
  "active_id": 269,
  "active_name": "Iono's Bellibolt ex",
  "active_energy_count": 4,
  "selected_option_type": 10,
  "selected_option_class": "ability",
  "available_attack_ids": [368],
  "expected_action": "attack",
  "actual_action": "ability_then_no_attack",
  "why_suspicious": "A legal attack was available, but the turn ended without an attack.",
  "confidence": "medium",
  "suggested_fix_area": [
    "strategy_engine.score_ability_option",
    "policy.py final_score integration"
  ],
  "related_events": []
}
```

---

## Markdown Report

出力先:

```text
reports/latest_anomaly_report.md
```

構造:

```md
# Battle Log Anomaly Report

## Summary

| Metric | Count |
|---|---:|

## Severity Breakdown

| Severity | Count |
|---|---:|

## Top Issues

### 1. attack_available_but_no_attack

- count:
- likely fix area:

## Representative Anomalies

### A0001

- severity:
- type:
- file:
- turn:
- active:
- expected:
- actual:
- why suspicious:
- suggested fix area:

## Suggested Next Actions
```

---

## LLM Review Packet

出力先:

```text
reports/latest_anomaly_summary.md
```

短く、Claude Code / Codex / ChatGPT が読みやすい形式にする。

```md
# LLM Review Packet

## Summary

- total anomalies:
- critical:
- high:
- most common issue:
- likely fix area:

## Top 10 Anomalies

### A0001
- type:
- severity:
- active:
- expected:
- actual:
- why suspicious:
- suggested fix area:

## Ask

Please identify:
1. likely root cause
2. file to inspect
3. profile or weight change candidate
4. whether code change is needed
5. whether an A/B simulation is required
```

---

## Future Phases

### Phase 2: LLM Review Support

追加:

```text
root cause candidate
likely responsible file
profile-only fix candidate
code-change-required flag
confidence
```

### Phase 3: A/B Evaluation

作成候補:

```text
tools/compare_anomaly_reports.py
```

目的:

```text
before report
after report
→ anomaly件数と主要指標を比較
→ 改善/悪化を判定
```

### Phase 4: Fix Prompt Generation

作成候補:

```text
tools/generate_fix_prompt.py
reports/latest_fix_prompt.md
```

anomaly summary から Claude Code 向け修正指示を生成する。

ただし、自動patch適用はしない。

### Phase 5: MCP Integration

将来的に検討。

候補ツール:

```text
run_simulation
parse_latest_logs
detect_anomalies
get_top_anomalies
compare_before_after
generate_fix_prompt
```

MCP化はローカルCLIが安定してから実施する。

---

## Do Not Do in Phase 1

このフェーズでは以下をやらない。

```text
policy.py の変更
strategy_engine.py scoring の変更
ionos_rules.py scoring の変更
deck.csv の変更
LLM API呼び出し
MCP化
自動patch生成
自動採用
submission.tar.gz の再ビルド
```

---

## Acceptance Criteria for Phase 1

```text
battle_logs/inbox/ が存在する
tools/analyze_battle_logs.py が存在する
tools/detect_anomalies.py が存在する
tools/generate_anomaly_report.py が存在する
reports/latest_anomaly_report.json を生成できる
reports/latest_anomaly_report.md を生成できる
reports/latest_anomaly_summary.md を生成できる
type=12 を Attack として扱っていない
Ability をターン終了扱いしていない
可能な範囲で role/profile-aware な検知になっている
Iono's Lightning 専用実装になっていない
deck.csv が変更されていない
policy の行動ロジックが変更されていない
```

---

## Prompt to Run Phase 1 in Claude Code

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Battle Log Diagnostic Pipeline MVP Phase 1

## 必ず読むファイル

- CLAUDE.md
- docs/instructions/20260619_battle_log_diagnostic_pipeline.md
- docs/phase_plan_profile_strategy.md
- data/deck_profile.json

## 目的

battle_logs/inbox/ に戦歴ログを置くだけで、問題点を自動検知して reports/ に出力できる仕組みを作ります。

この仕組みは現在の Iono's Lightning デッキ専用ではなく、他のデッキでも使える汎用構成にしてください。

## 作成するディレクトリ

- battle_logs/inbox/
- battle_logs/processed/
- battle_logs/ignored/
- reports/anomaly_reports/

必要に応じて `.gitkeep` を置いてください。

## 作成するファイル

- tools/analyze_battle_logs.py
- tools/detect_anomalies.py
- tools/generate_anomaly_report.py

## 実装すること

1. battle_logs/inbox/ から .json / .jsonl / .log を読み込む
2. ログを共通イベント形式へ正規化する
3. 同一ターン内の行動連鎖を追跡する
4. 汎用 anomaly を検知する
5. severity を付ける
6. suggested_fix_area を出す
7. reports/latest_anomaly_report.json を出力する
8. reports/latest_anomaly_report.md を出力する
9. reports/latest_anomaly_summary.md を出力する
10. 日付付きレポートを reports/anomaly_reports/ に保存する

## 検知する anomaly

- attack_available_but_no_attack
- end_when_attack_available
- retreat_when_attack_available
- ability_without_followup_attack
- high_value_attack_not_used
- ko_available_but_no_attack
- ability_breaks_attack_ready_state
- overattach_to_ready_attacker
- stage1_without_base_search
- duplicate_stage1_search
- low_value_search
- discarded_protected_card

## 守るルール

- simulator の select.option を合法手の正とする
- type=10 は Ability
- type=12 は Retreat
- type=13 + attackId のみ Attack
- type=14 は End
- type=12 を攻撃扱いしない
- Ability はターン終了扱いしない
- 同一ターン内で最終的に Attack したかを見る
- カード名・カードIDへの直書きは最小限にする
- deck_profile の roles / evolves_from / evolves_to / policy を使える場合は使う

## 今回やらないこと

- policy.py の変更
- strategy_engine.py のスコア変更
- ionos_rules.py のスコア変更
- deck.csv の変更
- MCP化
- LLM API呼び出し
- 自動patch生成
- submission.tar.gz の再ビルド

## 完了条件

- 指定ディレクトリが作成されている
- 指定ツールが作成されている
- analyze_battle_logs.py が実行できる
- reports/latest_anomaly_report.json が出力される
- reports/latest_anomaly_report.md が出力される
- reports/latest_anomaly_summary.md が出力される
- deck.csv が変更されていない
- 行動ロジックが変更されていない
- 変更ファイル一覧と実行方法を報告する
```
