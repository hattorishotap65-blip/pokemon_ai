# Claude Code Instruction: Level 3 Battle Log Anomaly Detection

## Purpose

Level 3 として、戦歴ログから異常行動を自動検知できる仕組みを実装する。

これまでに勝ち筋・デッキプロファイル・PDCA方針は整理済み。次の段階では、実際にログを読み込み、anomaly report を生成できる状態にする。

---

## Current Level

```text
Current: Level 2.5
Target: Level 3
```

Level 3 の定義:

```text
戦歴ログから異常行動を自動検知し、JSON / Markdown / LLM review summary として出力できる。
```

---

## Must Read First

実装前に必ず読むこと。

```text
CLAUDE.md
data/deck_profile.json
docs/instructions/20260619_battle_log_diagnostic_pipeline.md
docs/instructions/20260619_pdca_self_learning_loop.md
docs/instructions/20260619_10game_battle_log_review_retreat_priority.md
docs/instructions/20260619_voltorb_scaling_win_condition_correction.md
```

---

## Target Files to Create

以下を作成する。

```text
tools/analyze_battle_logs.py
tools/detect_anomalies.py
tools/generate_anomaly_report.py
```

必要に応じて以下のディレクトリも作る。

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
```

---

## CLI Requirements

最低限、以下で実行できるようにする。

```bash
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports
```

追加オプション:

```bash
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --top 20

python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --move-processed

python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --deck-profile data/deck_profile.json --top 20
```

ログが空でもエラーにせず、0件レポートを出すこと。

---

## Input Files

読み込み対象:

```text
.json
.jsonl
.log
```

対象ログは cabt の battle log を想定する。

読めないファイルがあっても全体を落とさない。読み取れないファイルは ignored として report に記録する。

---

## Universal Option Rules

必ず以下を守る。

```text
type=10 -> Ability
type=12 -> Retreat
type=13 + attackId -> Attack
type=14 -> End
```

重要ルール:

```text
- type=12 を Attack として扱わない
- type=13 かつ attackId がある場合のみ Attack
- Ability はターン終了扱いしない
- Attack と End はターン終了行動として扱う
- simulator の select.option を合法手の正とする
```

---

## Log Normalization

生ログを直接判定せず、まず共通イベント形式に正規化する。

正規化後のイベント例:

```json
{
  "file": "80571821.json",
  "game_id": "80571821",
  "turn": 19,
  "step": 123,
  "player": 0,
  "team_name": "family hattori",
  "phase": "select_action",
  "active_id": 270,
  "active_name": "Iono's Wattrel",
  "active_energy_count": 1,
  "available_options": [],
  "selected_option": {},
  "selected_option_type": 13,
  "selected_option_class": "attack",
  "has_legal_attack": true,
  "has_legal_retreat": true,
  "available_attack_ids": [],
  "bench": [],
  "hand": [],
  "discard": []
}
```

欠損フィールドがあっても落とさない。取得できない値は `null` または空配列にする。

---

## Turn Tracking

同一ターン内の行動連鎖を追跡する。

重要:

```text
Ability を使った直後に攻撃していないだけでは異常と断定しない。
同一ターンの最後まで追跡し、最終的に Attack したかを見る。
```

正常例:

```text
Attack optionあり
→ Ability
→ Energy attach
→ Attack
```

異常候補:

```text
Attack optionあり
→ Ability
→ End
```

---

## Required Anomaly Types

Level 3 で最低限検知するもの。

```text
attack_available_but_no_attack
end_when_attack_available
retreat_when_attack_available
ability_without_followup_attack
stage1_without_base_search
duplicate_stage1_search
overattach_to_ready_attacker
```

Voltorb勝ち筋補正として、可能なら以下も入れる。

```text
voltorb_scaling_attack_underused
best_damage_attacker_not_selected
```

ただし、Voltorb系はフィールド不足で確信度が低い場合、`confidence: low` として出す。

---

## Anomaly Definitions

### attack_available_but_no_attack

条件:

```text
- 同一ターン中に Attack option が存在した
- そのターン中に Attack が選択されなかった
```

severity:

```text
high
```

---

### end_when_attack_available

条件:

```text
- 現在の select.option に Attack option がある
- それにもかかわらず End を選択した
```

severity:

```text
high
```

---

### retreat_when_attack_available

条件:

```text
- 現在の select.option に Attack option がある
- それにもかかわらず Retreat を選択した
- ただし、将来の例外として stronger/best attacker pivot がある場合は confidence を下げる
```

severity:

```text
high
```

---

### ability_without_followup_attack

条件:

```text
- Ability を使用した
- その前後で Attack option が存在した
- 同一ターン中に最終的に Attack しなかった
```

Ability後に最終的にAttackしている場合は異常にしない。

severity:

```text
medium
```

---

### stage1_without_base_search

条件:

```text
- Stage1 / evolution Pokemon を検索・取得
- 対応する evolves_from が場にいない
```

deck_profile から evolves_from が取れない場合は無理に検知しない。

severity:

```text
medium
```

---

### duplicate_stage1_search

条件:

```text
- Stage1 / evolution Pokemon を検索・取得
- 同名カードがすでに手札にある
- 対応する進化元や必要盤面が不足している
```

severity:

```text
low / medium
```

---

### overattach_to_ready_attacker

条件:

```text
- すでに攻撃可能なアタッカーに追加エネルギーを付けた
- その添付がKOライン到達、打点上昇、後続準備に寄与していない
```

注意:

Voltorb scaling の場合、盤面全体の雷エネ数が打点に影響するため、単純な過剰添付扱いにしない。Iono's Pokemon への雷エネ添付は Voltorb打点上昇に寄与する可能性がある。

severity:

```text
medium
```

---

## Voltorb-Specific Detection

`data/deck_profile.json` に以下のような設定がある前提で使う。

```json
{
  "voltorb_scaling_policy": {
    "main_scaling_attacker": 265,
    "required_lightning_to_attack": 2,
    "damage_formula": "20 + 20 * total_lightning_energy_attached_to_own_iono_pokemon",
    "count_lightning_energy_on_card_ids": [265, 268, 269, 270, 271],
    "estimated_damage_high_threshold": 120
  }
}
```

### voltorb_scaling_attack_underused

条件:

```text
- Iono's Voltorb が Active または合法的に前に出せる可能性がある
- Voltorb が2エネ以上、または同一ターンで攻撃可能化できる
- 自分の Iono's Pokemon 全体の雷エネ数が多い
- 推定Voltorb打点が高い
- それにもかかわらず、低価値攻撃や不要なセットアップを優先している
```

推定打点:

```text
voltorb_damage = 20 + 20 * total_lightning_energy_attached_to_own_iono_pokemon
```

severity:

```text
medium
```

confidence:

```text
low / medium / high
```

ログから必要情報が不足する場合は `confidence: low` にする。

---

### best_damage_attacker_not_selected

条件:

```text
- 複数の攻撃候補、または合法的なpivot候補がある
- 片方が明らかに高い推定打点またはKO価値を持つ
- AIが明らかに低い攻撃を選択している
```

Iono's Lightning では Voltorb scaling damage を必ず考慮する。

---

## Report Output

以下を生成する。

```text
reports/latest_anomaly_report.json
reports/latest_anomaly_report.md
reports/latest_anomaly_summary.md
```

さらに履歴として日付付きファイルを保存する。

```text
reports/anomaly_reports/YYYYMMDD_HHMMSS_anomaly_report.json
reports/anomaly_reports/YYYYMMDD_HHMMSS_anomaly_report.md
```

---

## JSON Report Schema

```json
{
  "schema_version": "1.0",
  "source_dir": "battle_logs/inbox",
  "deck_profile_id": "ionos_kilowattrel",
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
    "stage1_without_base_search": 0,
    "duplicate_stage1_search": 0,
    "overattach_to_ready_attacker": 0,
    "voltorb_scaling_attack_underused": 0,
    "best_damage_attacker_not_selected": 0
  },
  "anomalies": [],
  "ignored_files": []
}
```

各 anomaly 例:

```json
{
  "id": "A0001",
  "severity": "medium",
  "type": "voltorb_scaling_attack_underused",
  "file": "80571821.json",
  "game_id": "80571821",
  "turn": 19,
  "player": 0,
  "active_id": 270,
  "active_name": "Iono's Wattrel",
  "expected_action": "consider_voltorb_scaling_attack_or_best_damage_attacker",
  "actual_action": "attack_with_lower_value_attacker",
  "why_suspicious": "Voltorb scaling damage may have been a better prize-race attack line.",
  "confidence": "low",
  "suggested_fix_area": [
    "tools/detect_anomalies.py",
    "data/deck_profile.json",
    "agent/strategy_engine.py"
  ],
  "related_events": []
}
```

---

## Markdown Report

`reports/latest_anomaly_report.md` は人間が読みやすい形式にする。

構成:

```md
# Battle Log Anomaly Report

## Summary

| Metric | Count |
|---|---:|

## Severity Breakdown

| Severity | Count |
|---|---:|

## Top Issues

### attack_available_but_no_attack

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
- confidence:
- suggested fix area:

## Suggested Next Actions
```

---

## LLM Review Summary

`reports/latest_anomaly_summary.md` は Claude Code / ChatGPT に渡しやすい短い形式にする。

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
5. whether A/B simulation is required
```

---

## Implementation Notes

### tools/analyze_battle_logs.py

役割:

```text
- CLI entrypoint
- input dir を走査
- ログ読み込み
- normalize
- detect_anomalies.py を呼ぶ
- generate_anomaly_report.py を呼ぶ
- reports に出力
```

### tools/detect_anomalies.py

役割:

```text
- 正規化イベントから anomaly を検知
- option type分類
- turn tracking
- deck_profile利用
- Voltorb scaling推定
```

### tools/generate_anomaly_report.py

役割:

```text
- JSON report作成
- Markdown report作成
- LLM summary作成
- 日付付きreport保存
```

---

## Testing Commands

実装後に最低限以下を実行する。

```bash
python tools/analyze_battle_logs.py --help
```

ログが空でも実行できること。

```bash
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --top 20
```

サンプルログを置いた場合:

```bash
python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --deck-profile data/deck_profile.json --top 20
```

確認する出力:

```text
reports/latest_anomaly_report.json
reports/latest_anomaly_report.md
reports/latest_anomaly_summary.md
```

---

## Do Not Do

このLevel 3では以下をやらない。

```text
- deck.csv の変更
- policy.py の変更
- agent本体の行動変更
- strategy_engine.py のスコア変更
- submission.tar.gz の再ビルド
- 自動patch生成
- 自動merge
- LLM API呼び出し
```

Level 3 の目的は **検知とレポート化** であり、行動改善は次フェーズで行う。

---

## Acceptance Criteria

Level 3 完了条件:

```text
- tools/analyze_battle_logs.py が存在する
- tools/detect_anomalies.py が存在する
- tools/generate_anomaly_report.py が存在する
- battle_logs/inbox/ が存在する
- reports/anomaly_reports/ が存在する
- 空ログでもレポート生成できる
- cabt jsonログを読み込める
- type=12をAttack扱いしていない
- Abilityをターン終了扱いしていない
- attack_available_but_no_attack を検知できる
- end_when_attack_available を検知できる
- retreat_when_attack_available を検知できる
- ability_without_followup_attack を検知できる
- reports/latest_anomaly_report.json が生成される
- reports/latest_anomaly_report.md が生成される
- reports/latest_anomaly_summary.md が生成される
- deck.csv が変更されていない
- policy.py が変更されていない
```

Voltorb関連の追加達成条件:

```text
- data/deck_profile.json の voltorb_scaling_policy を読み込める
- Voltorb推定打点を計算する関数がある
- 情報不足時は confidence low で扱える
- voltorb_scaling_attack_underused を出せる構造がある
```

---

## Claude Code Prompt

以下を Claude Code に渡して実行する。

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Level 3: Battle Log Anomaly Detection

## 必ず読むファイル

- CLAUDE.md
- data/deck_profile.json
- docs/instructions/20260619_battle_log_diagnostic_pipeline.md
- docs/instructions/20260619_pdca_self_learning_loop.md
- docs/instructions/20260619_10game_battle_log_review_retreat_priority.md
- docs/instructions/20260619_voltorb_scaling_win_condition_correction.md
- docs/instructions/20260619_level3_battle_log_anomaly_detection.md

## 目的

戦歴ログから異常行動を自動検知し、JSON / Markdown / LLM review summary を出力できるようにする。

## 作成するファイル

- tools/analyze_battle_logs.py
- tools/detect_anomalies.py
- tools/generate_anomaly_report.py

## 作成するディレクトリ

- battle_logs/inbox/
- battle_logs/processed/
- battle_logs/ignored/
- reports/anomaly_reports/

必要なら .gitkeep を置いてください。

## 実装すること

1. battle_logs/inbox/ から .json / .jsonl / .log を読む
2. cabt battle log を落ちずに解析する
3. select.option を正として option type を分類する
4. 同一ターン内の行動を追跡する
5. anomaly を検知する
6. severity / confidence / suggested_fix_area を付ける
7. reports/latest_anomaly_report.json を出す
8. reports/latest_anomaly_report.md を出す
9. reports/latest_anomaly_summary.md を出す
10. reports/anomaly_reports/ に日付付き履歴を保存する

## 必須検知

- attack_available_but_no_attack
- end_when_attack_available
- retreat_when_attack_available
- ability_without_followup_attack
- stage1_without_base_search
- duplicate_stage1_search
- overattach_to_ready_attacker

## 可能なら追加

- voltorb_scaling_attack_underused
- best_damage_attacker_not_selected

## 守るルール

- type=10 は Ability
- type=12 は Retreat
- type=13 + attackId のみ Attack
- type=14 は End
- type=12 を Attack として扱わない
- Ability はターン終了扱いしない
- Attack と End はターン終了扱い
- simulator の select.option を合法手の正とする
- Voltorb scaling は data/deck_profile.json の voltorb_scaling_policy を使う

## 今回やらないこと

- deck.csv の変更
- policy.py の変更
- agent本体の行動変更
- strategy_engine.py のスコア変更
- submission.tar.gz の再ビルド
- 自動修正
- 自動merge

## 実行確認

以下を実行してください。

python tools/analyze_battle_logs.py --help

python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports --top 20

## 完了条件

- 上記コマンドが通る
- reports/latest_anomaly_report.json が生成される
- reports/latest_anomaly_report.md が生成される
- reports/latest_anomaly_summary.md が生成される
- 空ログでも落ちない
- deck.csv が変更されていない
- policy.py が変更されていない
- 変更ファイル一覧と実行結果を報告する
```
