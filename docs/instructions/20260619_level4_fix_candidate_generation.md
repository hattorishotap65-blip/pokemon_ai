# Claude Code Instruction: Level 4 Fix Candidate Generation

## Purpose

Level 4 として、Level 3 の anomaly report から修正候補を生成できる仕組みを実装する。

このフェーズでは、AI本体の挙動はまだ変更しない。  
`reports/latest_anomaly_report.json` を読み、異常の種類・重要度・頻度・代表例を分類し、次に修正すべき候補と Claude Code に渡せる修正プロンプトを生成する。

デッキ破壊 / ライブラリーアウト検討はいったん対象外とし、現在の Iono's Lightning / Voltorb scaling 方針を継続する。

---

## Current Level

```text
Current: Level 3.5
Target: Level 4
```

Level 4 の定義:

```text
Level 3 の検知結果から、修正候補・修正対象ファイル・リスク・A/Bテスト要否・Claude Code向け修正プロンプトを自動生成できる。
```

---

## Scope

このPR/フェーズでやること:

```text
- anomaly report を読み込む
- anomaly を分類する
- root cause 候補を推定する
- 修正候補を JSON / Markdown に出力する
- Claude Code に渡せる latest_fix_prompt.md を生成する
```

このPR/フェーズでやらないこと:

```text
- deck.csv の変更
- policy.py の直接変更
- strategy_engine.py の直接変更
- ionos_rules.py の直接変更
- agent本体の挙動変更
- A/Bテスト実行
- 重みの自動探索
- submission.tar.gz の再ビルド
- 自動commit / 自動merge
```

Level 4 は **修正案生成まで**。  
実際の修正適用は、生成された fix prompt を人間が確認してから次フェーズで実施する。

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
docs/instructions/20260619_level3_battle_log_anomaly_detection.md
```

---

## Input

Level 3 で生成された以下を入力とする。

```text
reports/latest_anomaly_report.json
reports/latest_anomaly_report.md
reports/latest_anomaly_summary.md
```

最低限必要なのは `reports/latest_anomaly_report.json`。

入力ファイルが存在しない場合は、落とさずに分かりやすいエラーメッセージを出す。

---

## Target Files to Create

以下を作成する。

```text
tools/generate_fix_prompt.py
tools/classify_anomalies.py
```

必要に応じて以下のディレクトリを作成する。

```text
reports/
  fix_prompts/
    .gitkeep
```

---

## CLI Requirements

最低限、以下で実行できるようにする。

```bash
python tools/generate_fix_prompt.py \
  --input reports/latest_anomaly_report.json \
  --output reports
```

追加オプション:

```bash
python tools/generate_fix_prompt.py \
  --input reports/latest_anomaly_report.json \
  --output reports \
  --top 20

python tools/generate_fix_prompt.py \
  --input reports/latest_anomaly_report.json \
  --output reports \
  --focus best_damage_attacker_not_selected

python tools/generate_fix_prompt.py \
  --input reports/latest_anomaly_report.json \
  --output reports \
  --deck-profile data/deck_profile.json \
  --top 20
```

---

## Output Files

以下を生成する。

```text
reports/latest_fix_candidates.json
reports/latest_fix_candidates.md
reports/latest_fix_prompt.md
```

さらに履歴として日付付きファイルを保存する。

```text
reports/fix_prompts/YYYYMMDD_HHMMSS_fix_candidates.json
reports/fix_prompts/YYYYMMDD_HHMMSS_fix_candidates.md
reports/fix_prompts/YYYYMMDD_HHMMSS_fix_prompt.md
```

---

## Fix Candidate JSON Schema

`reports/latest_fix_candidates.json` は以下の構造にする。

```json
{
  "schema_version": "1.0",
  "source_report": "reports/latest_anomaly_report.json",
  "deck_profile_id": "ionos_kilowattrel",
  "summary": {
    "anomalies_total": 0,
    "candidate_total": 0,
    "high_priority_candidates": 0,
    "medium_priority_candidates": 0,
    "low_priority_candidates": 0
  },
  "classification": {},
  "fix_candidates": []
}
```

各 fix candidate は以下の構造にする。

```json
{
  "id": "F0001",
  "priority": "high",
  "source_anomaly_type": "best_damage_attacker_not_selected",
  "classification": "voltorb_over_kilowattrel_missed",
  "title": "Prefer Voltorb scaling attack over low-damage Kilowattrel when Voltorb has high estimated damage",
  "root_cause_hypothesis": "Attacker selection currently underweights Voltorb scaling damage compared with static attacker priority.",
  "evidence": {
    "count": 31,
    "representative_anomaly_ids": ["A0001", "A0002"],
    "actual_attackers": [271],
    "estimated_voltorb_damage_range": [160, 200]
  },
  "suggested_change_type": "scoring_adjustment",
  "suggested_target_files": [
    "data/deck_profile.json",
    "ionos_rules.py",
    "policy.py"
  ],
  "risk": "medium",
  "expected_effect": "Increase selection rate of Voltorb when it is the better prize-efficient attacker.",
  "do_not_change": [
    "deck.csv",
    "submission.tar.gz"
  ],
  "requires_ab_test": true,
  "ab_test_metric": [
    "win_rate",
    "best_damage_attacker_not_selected",
    "voltorb_attack_count",
    "avg_prize_trade_efficiency"
  ],
  "claude_code_prompt": "..."
}
```

---

## Required Classification Logic

### General classification

全 anomaly を以下の観点で分類する。

```text
- anomaly type
- severity
- confidence
- occurrence count
- actual selected action
- actual attacker card id
- estimated damage if available
- suggested fix area
- risk of changing behavior
```

分類結果は `classification` にまとめる。

---

## Special Focus: best_damage_attacker_not_selected

直近の Level 3 検証では、以下の内訳が出ている。

```text
best_damage_attacker_not_selected: 156件 low

actual attacker breakdown:
- Bellibolt ex / 269: 124件
- Kilowattrel / 271: 31件
- Wattrel / 270: 1件
```

この anomaly はそのまま全件修正対象にしてはいけない。  
Level 4 では、必ず以下の分類に分ける。

```text
1. voltorb_over_kilowattrel_missed
2. voltorb_over_wattrel_missed
3. bellibolt_over_voltorb_high_damage
4. bellibolt_attack_probably_correct
5. unknown_due_to_missing_pivot_or_energy_info
```

---

### 1. voltorb_over_kilowattrel_missed

条件:

```text
- source anomaly type = best_damage_attacker_not_selected
- actual attacker = Kilowattrel / 271
- estimated_voltorb_damage >= 120
```

優先度:

```text
medium〜high
```

理由:

```text
Kilowattrel の固定70ダメージより Voltorb scaling damage が明らかに高い可能性がある。
```

ただし、Voltorb が攻撃可能か、前に出せるかが不明な場合は risk を medium にし、prompt 内で確認条件を明記する。

---

### 2. voltorb_over_wattrel_missed

条件:

```text
- source anomaly type = best_damage_attacker_not_selected
- actual attacker = Wattrel / 270
- estimated_voltorb_damage >= 100
```

優先度:

```text
high
```

理由:

```text
進化前Wattrelで攻撃している一方、Voltorbの推定打点が十分高い場合は改善余地が大きい。
```

---

### 3. bellibolt_over_voltorb_high_damage

条件:

```text
- source anomaly type = best_damage_attacker_not_selected
- actual attacker = Bellibolt ex / 269
- estimated_voltorb_damage > 230
```

優先度:

```text
medium
```

理由:

```text
Bellibolt ex は固定230ダメージだが、Voltorbの推定打点が230を超える場合は、非exかつ高打点のVoltorbがより良い可能性がある。
```

ただし、Bellibolt ex でしかKOできない、Voltorbが前に出せない、Voltorbが攻撃不能の場合は修正対象外にする。

---

### 4. bellibolt_attack_probably_correct

条件:

```text
- source anomaly type = best_damage_attacker_not_selected
- actual attacker = Bellibolt ex / 269
- estimated_voltorb_damage <= 230
```

優先度:

```text
low or no-fix
```

理由:

```text
単純打点ではBellibolt exの230が同等以上であり、これを修正対象にすると逆に弱くなる可能性がある。
```

この分類は fix candidate ではなく、detector refinement candidate として扱う。

---

### 5. unknown_due_to_missing_pivot_or_energy_info

条件:

```text
- Voltorbの推定打点は高い
- しかしVoltorbが攻撃可能か、前に出せるか、必要エネルギーがあるか判断できない
```

優先度:

```text
low
```

対応:

```text
スコア修正ではなく、Level 3 detector の情報量改善候補にする。
```

---

## Candidate Priority Rules

fix candidate の優先度は以下で決める。

```text
high:
- critical/high anomaly が多い
- 明らかな誤行動
- win rate に直結する可能性が高い
- 修正対象が狭い

medium:
- 件数が多い
- 改善可能性がある
- ただし誤修正リスクもある

low:
- confidence low
- 情報不足
- detector refinement だけで十分な可能性が高い
```

---

## Required Candidate Types

少なくとも以下の candidate type を生成できるようにする。

```text
scoring_adjustment
profile_adjustment
detector_refinement
logging_improvement
no_fix_needed
```

### scoring_adjustment

AI本体の行動選択スコアを調整する候補。

例:

```text
Voltorb推定打点が高いとき、Kilowattrel攻撃よりVoltorb攻撃を優先する。
```

### profile_adjustment

`data/deck_profile.json` の方針・閾値・役割を調整する候補。

例:

```text
voltorb_high_damage_threshold を120から160へ調整する。
```

### detector_refinement

Level 3 detector の誤検知を減らす候補。

例:

```text
Bellibolt ex攻撃でVoltorb推定打点 <= 230の場合は best_damage_attacker_not_selected を出さない。
```

### logging_improvement

ログに不足している情報を追加する候補。

例:

```text
Voltorbがベンチから前に出せたか、必要エネがあったかをログに出す。
```

### no_fix_needed

正常動作と見なす候補。

例:

```text
Bellibolt exでしかKOできないため、Bellibolt攻撃は妥当。
```

---

## Markdown Report Requirements

`reports/latest_fix_candidates.md` は人間が読みやすい形式にする。

構成例:

```md
# Fix Candidate Report

## Summary

| Metric | Count |
|---|---:|

## Classification Summary

| Classification | Count | Suggested Action |
|---|---:|---|

## Fix Candidates

### F0001: Prefer Voltorb over Kilowattrel when scaling damage is high

- priority:
- source anomaly:
- classification:
- evidence:
- root cause hypothesis:
- suggested target files:
- risk:
- expected effect:
- requires A/B test:

## No-Fix / Detector Refinement Candidates

## Next Recommended Action
```

---

## latest_fix_prompt.md Requirements

`reports/latest_fix_prompt.md` は、そのまま Claude Code に渡せる形式にする。

必ず以下を含める。

```text
- 対象フェーズ
- 必ず読むファイル
- 修正候補ID
- 修正目的
- 根拠となる anomaly
- 変更してよいファイル
- 変更してはいけないファイル
- 実装方針
- 実行コマンド
- 完了条件
- A/Bテストで確認する指標
```

ただし、この prompt は **1つの修正候補に絞る**。  
複数候補を同時に修正しない。

優先候補が複数ある場合、最初の `latest_fix_prompt.md` は以下を優先する。

```text
1. voltorb_over_wattrel_missed
2. voltorb_over_kilowattrel_missed
3. bellibolt_over_voltorb_high_damage
4. detector_refinement for Bellibolt false positives
```

---

## Recommended First Fix Candidate

現時点では、最初の候補は以下を推奨する。

```text
voltorb_over_kilowattrel_missed
```

理由:

```text
- Kilowattrel は固定70ダメージ
- Voltorb推定160〜200が出ているケースがある
- Bellibolt ex 124件より誤修正リスクが低い
- Voltorb scaling の勝ち筋と一致する
```

ただし、修正promptには以下の条件を必ず入れる。

```text
Voltorbが実際に攻撃可能、または合法的に前に出せる場合に限って優先する。
```

---

## Claude Code Prompt to Implement Level 4

以下を Claude Code に渡して実装する。

```md
次のフェーズだけ実施してください。
他のフェーズには進まないでください。

## 対象フェーズ

Level 4: Fix Candidate Generation

## 必ず読むファイル

- CLAUDE.md
- data/deck_profile.json
- docs/instructions/20260619_battle_log_diagnostic_pipeline.md
- docs/instructions/20260619_pdca_self_learning_loop.md
- docs/instructions/20260619_level3_battle_log_anomaly_detection.md
- docs/instructions/20260619_level4_fix_candidate_generation.md
- tools/analyze_battle_logs.py
- tools/detect_anomalies.py
- tools/generate_anomaly_report.py

## 目的

Level 3 が生成した reports/latest_anomaly_report.json を読み取り、修正候補を分類・生成し、以下を出力できるようにしてください。

- reports/latest_fix_candidates.json
- reports/latest_fix_candidates.md
- reports/latest_fix_prompt.md
- reports/fix_prompts/YYYYMMDD_HHMMSS_fix_candidates.json
- reports/fix_prompts/YYYYMMDD_HHMMSS_fix_candidates.md
- reports/fix_prompts/YYYYMMDD_HHMMSS_fix_prompt.md

## 作成するファイル

- tools/classify_anomalies.py
- tools/generate_fix_prompt.py

## 実装すること

1. reports/latest_anomaly_report.json を読む
2. anomaly type / severity / confidence / actual attacker / estimated damage で分類する
3. best_damage_attacker_not_selected を以下に細分化する
   - voltorb_over_kilowattrel_missed
   - voltorb_over_wattrel_missed
   - bellibolt_over_voltorb_high_damage
   - bellibolt_attack_probably_correct
   - unknown_due_to_missing_pivot_or_energy_info
4. 修正候補を priority / risk / suggested_target_files / requires_ab_test 付きで生成する
5. no-fix / detector refinement も候補として明示する
6. 最優先候補1件に絞った latest_fix_prompt.md を生成する
7. 複数の修正を同時に実施しないよう prompt に明記する

## 今回やらないこと

- deck.csv の変更
- policy.py の変更
- ionos_rules.py の変更
- strategy_engine.py の変更
- agent本体の行動変更
- A/Bテスト実行
- submission.tar.gz の再ビルド
- 自動修正
- 自動merge
- デッキ破壊 / ライブラリーアウト系の検討

## 実行コマンド

python tools/generate_fix_prompt.py \
  --input reports/latest_anomaly_report.json \
  --output reports \
  --deck-profile data/deck_profile.json \
  --top 20

## 完了条件

- 上記コマンドが通る
- reports/latest_fix_candidates.json が生成される
- reports/latest_fix_candidates.md が生成される
- reports/latest_fix_prompt.md が生成される
- best_damage_attacker_not_selected が attacker別に分類される
- Bellibolt ex の明らかに妥当な攻撃は no-fix または detector refinement として扱われる
- Kilowattrel / Wattrel への低打点攻撃は修正候補として上位に出る
- deck.csv / policy.py / ionos_rules.py / strategy_engine.py は変更されていない
- 変更ファイル一覧と実行結果を報告する
```

---

## Acceptance Criteria

Level 4 完了条件:

```text
- tools/classify_anomalies.py が存在する
- tools/generate_fix_prompt.py が存在する
- reports/latest_anomaly_report.json を入力にできる
- reports/latest_fix_candidates.json が生成される
- reports/latest_fix_candidates.md が生成される
- reports/latest_fix_prompt.md が生成される
- best_damage_attacker_not_selected を細分化できる
- fix candidate に priority / risk / target files / A/B metric が含まれる
- no-fix / detector refinement を明示できる
- latest_fix_prompt.md が1候補に絞られている
- agent本体の挙動は変更されていない
```

---

## Next Phase After Level 4

Level 4 が完了したら、次は Level 5 に進む。

```text
Level 5:
生成された修正候補を1つだけ適用し、baseline と candidate をA/B比較する。
```

Level 4 の段階で修正を直接適用しないこと。
