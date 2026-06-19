# Claude Code Instruction: PDCA Self-Learning Loop

## Purpose

戦歴ログの診断結果をもとに、AIの改善候補を継続的に作成・評価するための **半自動PDCA / 自己学習風ループ** を作成する。

この指示は Claude Code 向けです。

重要: このフェーズでは、AIが勝手に自分自身を修正して自動採用する仕組みは作らない。まずは、診断レポートを入力として、改善候補を作り、before / after を比較し、人が判断できる材料を出すところまでを対象にする。

---

## Background

既存の次フェーズとして扱う。

```text
docs/instructions/20260619_battle_log_diagnostic_pipeline.md
```

既存フェーズでは、戦歴ログを解析して以下を出力する想定である。

```text
reports/latest_anomaly_report.json
reports/latest_anomaly_report.md
reports/latest_anomaly_summary.md
```

今回のフェーズでは、これらの anomaly report を使って、改善候補を作り、A/B比較して、採用判断につなげる。

---

## Goal

最終的に目指す流れは以下。

```text
battle_logs/inbox/
→ analyze_battle_logs.py
→ latest_anomaly_report.json / md
→ latest_anomaly_summary.md
→ generate_fix_prompt.py
→ Claude Code implementation branch
→ run baseline / candidate simulations
→ compare_anomaly_reports.py
→ latest_ab_comparison.json / md
→ accept / reject / needs_more_games / human_review
```

ただし、最初から全自動にしない。

---

## Core Principle

```text
Observe first.
Hypothesize second.
Patch carefully.
Compare before accepting.
Never auto-merge.
```

この仕組みは「自己学習っぽい」改善サイクルを目指すが、厳密な強化学習やオンライン学習ではない。

安全な実装方針:

```text
- ログから問題を検知する
- 問題の種類を集計する
- 改善すべき領域を推定する
- Claude Code向けの修正プロンプトを生成する
- 修正前後の結果を比較する
- 採用判断を人間に渡す
```

---

## Do Not Change

このPRまたはこの指示フェーズでは、以下を変更しない。

```text
- deck.csv
- policy.py
- strategy_engine.py
- agent本体の行動ロジック
- scoring weight の実値
- submission archive
- 既存PRの内容
```

今回追加するのは Claude Code 向けの指示書のみ。

---

## PDCA Model

### Plan

anomaly report から改善対象を選ぶ。

入力:

```text
reports/latest_anomaly_report.json
reports/latest_anomaly_report.md
reports/latest_anomaly_summary.md
```

見るべき観点:

```text
- high / critical anomaly の件数
- attack_available_but_no_attack の件数
- end_when_attack_available の件数
- ability_without_followup_attack の件数
- overattach_to_ready_attacker の件数
- stage1_without_base_search の件数
- duplicate_stage1_search の件数
- suggested_fix_area の集中箇所
```

出力イメージ:

```json
{
  "top_problem": "attack_available_but_no_attack",
  "suspected_fix_area": [
    "strategy_engine.score_attack_option",
    "policy.py final_score integration",
    "turn_rule_engine.py"
  ],
  "priority": "high",
  "reason": "Attack was available in multiple turns but the agent ended without attacking."
}
```

---

### Do

改善候補を作る。

最初は自動でコードを書き換えない。Claude Codeに渡すための修正指示を生成する。

出力候補:

```text
reports/latest_fix_prompt.md
reports/fix_prompts/YYYYMMDD_HHMMSS_fix_prompt.md
```

修正指示には以下を含める。

```text
- 検知された問題
- 代表的な anomaly
- 改善対象ファイル候補
- 変更してよい範囲
- 変更してはいけない範囲
- acceptance criteria
- A/B比較で見る指標
```

---

### Check

修正前後の anomaly report を比較する。

入力:

```text
reports/baseline/latest_anomaly_report.json
reports/candidate/latest_anomaly_report.json
```

または CLI 引数で明示する。

```bash
python tools/compare_anomaly_reports.py \
  --before reports/baseline/latest_anomaly_report.json \
  --after reports/candidate/latest_anomaly_report.json \
  --output reports
```

比較対象:

```text
- total anomalies
- critical count
- high count
- medium count
- attack_available_but_no_attack
- end_when_attack_available
- retreat_when_attack_available
- ability_without_followup_attack
- overattach_to_ready_attacker
- stage1_without_base_search
- duplicate_stage1_search
```

出力:

```text
reports/latest_ab_comparison.json
reports/latest_ab_comparison.md
```

---

### Act

採用判断を出す。

判定は以下のいずれか。

```text
accept
reject
needs_more_games
human_review
```

原則:

```text
- high / critical が明確に減ったら accept 候補
- total anomalies が減っても critical / high が増えたら reject 候補
- ゲーム数が少ない場合は needs_more_games
- 指標が割れている場合は human_review
```

---

## Required Future Directory Structure

将来的には以下を想定する。

```text
reports/
  baseline/
    latest_anomaly_report.json
    latest_anomaly_report.md
  candidate/
    latest_anomaly_report.json
    latest_anomaly_report.md
  comparisons/
    .gitkeep
  fix_prompts/
    .gitkeep
  latest_ab_comparison.json
  latest_ab_comparison.md
  latest_fix_prompt.md

learning/
  .gitkeep
  decisions.jsonl
  weight_profile.example.json
  experiments.jsonl
```

この指示書追加PRでは、まだディレクトリ作成までは必須にしない。

---

## Candidate Tools

将来的に作成する候補ツール。

```text
tools/compare_anomaly_reports.py
tools/generate_fix_prompt.py
tools/run_pdca_cycle.py
tools/optimize_weights.py
```

役割:

```text
compare_anomaly_reports.py
  before / after の anomaly report を比較し、改善・悪化・判断保留を出す。

generate_fix_prompt.py
  anomaly summary から Claude Code 向けの修正プロンプトを生成する。

run_pdca_cycle.py
  analyze → prompt generation → comparison → decision をまとめる将来用CLI。

optimize_weights.py
  weight_profile を用いた探索。将来フェーズ扱い。MVPでは作らない。
```

---

## MVP Phase 1: Comparison Only

まず作るべき最小機能は、before / after の比較だけ。

### Create

```text
tools/compare_anomaly_reports.py
```

### CLI

```bash
python tools/compare_anomaly_reports.py \
  --before reports/baseline/latest_anomaly_report.json \
  --after reports/candidate/latest_anomaly_report.json \
  --output reports
```

任意引数:

```bash
python tools/compare_anomaly_reports.py \
  --before reports/baseline/latest_anomaly_report.json \
  --after reports/candidate/latest_anomaly_report.json \
  --output reports \
  --min-games 20
```

### Input schema assumption

既存 anomaly report の summary を読む。

```json
{
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
  }
}
```

欠損キーは 0 として扱う。

---

## A/B Comparison JSON Output

出力先:

```text
reports/latest_ab_comparison.json
```

構造例:

```json
{
  "schema_version": "1.0",
  "before": "reports/baseline/latest_anomaly_report.json",
  "after": "reports/candidate/latest_anomaly_report.json",
  "summary": {
    "decision": "human_review",
    "overall_delta": -5,
    "critical_delta": 0,
    "high_delta": -2,
    "medium_delta": -3,
    "low_delta": 0,
    "games_before": 20,
    "games_after": 20,
    "confidence": "medium"
  },
  "metrics": [
    {
      "name": "attack_available_but_no_attack",
      "before": 8,
      "after": 3,
      "delta": -5,
      "direction": "improved"
    }
  ],
  "reasons": [
    "High severity anomalies decreased.",
    "No critical anomaly increase was observed."
  ],
  "warnings": []
}
```

---

## A/B Comparison Markdown Output

出力先:

```text
reports/latest_ab_comparison.md
```

内容例:

```md
# A/B Anomaly Comparison

## Decision

human_review

## Summary

- Total anomalies: 30 -> 25 (-5)
- Critical: 0 -> 0 (0)
- High: 8 -> 6 (-2)
- Medium: 12 -> 9 (-3)

## Improved

- attack_available_but_no_attack: 8 -> 3 (-5)

## Worsened

- overattach_to_ready_attacker: 1 -> 2 (+1)

## Warnings

- Candidate game count is below min-games threshold.

## Recommendation

Run more games before accepting.
```

---

## Decision Rules

### accept

以下を満たす場合。

```text
- games_after >= min_games
- critical が増えていない
- high が増えていない
- total anomalies が減っている
- 主要ターゲット anomaly が減っている
```

### reject

以下の場合。

```text
- critical が増えた
- high が大幅に増えた
- total anomalies が増えた
- 改善対象の anomaly は減ったが、より重大な anomaly が増えた
```

### needs_more_games

以下の場合。

```text
- games_before または games_after が min_games 未満
- actions / turns が少なすぎる
- anomaly 数の差が小さく偶然の可能性が高い
```

### human_review

以下の場合。

```text
- 改善と悪化が混在している
- total は改善したが high が横ばい
- target は改善したが別の medium が増えている
- 判断が一意にできない
```

---

## MVP Phase 2: Fix Prompt Generation

MVP Phase 1 のあとに実装する。

### Create

```text
tools/generate_fix_prompt.py
```

### Input

```text
reports/latest_anomaly_report.json
reports/latest_anomaly_summary.md
```

### Output

```text
reports/latest_fix_prompt.md
reports/fix_prompts/YYYYMMDD_HHMMSS_fix_prompt.md
```

### Prompt contents

```md
# Claude Code Fix Prompt

## Problem

Describe the detected anomaly pattern.

## Evidence

List top anomalies and representative examples.

## Suspected fix area

List suggested_fix_area from anomaly report.

## Scope

Allowed changes.

## Do not change

Forbidden changes.

## Acceptance criteria

Expected reduction in anomaly metrics.

## A/B evaluation

How to compare before / after.
```

---

## MVP Phase 3: Weight Profile Candidates

将来、重み調整を安全に試すための profile を導入する。

候補ファイル:

```text
learning/weight_profile.example.json
```

構造例:

```json
{
  "schema_version": "1.0",
  "profile_id": "default",
  "weights": {
    "attack_available_bonus": 150.0,
    "end_when_attack_available_penalty": -1000.0,
    "retreat_when_attack_available_penalty": -1000.0,
    "ability_without_followup_attack_penalty": -200.0,
    "overattach_to_ready_attacker_penalty": -120.0,
    "stage1_without_base_search_penalty": -200.0
  },
  "notes": [
    "Example only. Do not apply automatically."
  ]
}
```

MVP Phase 3でも、重みを自動採用しない。

---

## Future Phase: Optimization

将来的には以下を検討できる。

```text
- random search
- grid search
- Optuna
- Bayesian optimization
- multi-game evaluation
- matchup-separated evaluation
- opening-hand-separated evaluation
```

ただし、以下を守ること。

```text
- deck.csv は変更しない
- 候補profileを直接本番採用しない
- A/B比較を必ず行う
- critical / high の悪化を最優先で防ぐ
- 勝率だけで判断しない
- anomaly の質も見る
```

---

## Future Phase: MCP Tooling

将来的に Claude Code / Codex から使いやすくする場合、以下をMCP化できる。

```text
run_simulation
analyze_battle_logs
compare_anomaly_reports
generate_fix_prompt
summarize_learning_decision
```

MCP化はこのフェーズでは不要。

---

## Safety Rules

必ず守る。

```text
- 自動で policy.py を変更しない
- 自動で strategy_engine.py を変更しない
- 自動で deck.csv を変更しない
- 自動で commit / push / merge しない
- LLM API をローカルツールから直接呼ばない
- Claude Code用のプロンプト生成に留める
- A/B評価なしで改善を採用しない
- 1回のログだけで改善確定しない
- critical / high anomaly の悪化を無視しない
```

---

## Claude Code Prompt for MVP Phase 1

MVP Phase 1 を実装させる場合は、以下を Claude Code に渡す。

```md
このmdを読んで、MVP Phase 1だけを実装してください。

対象:
- tools/compare_anomaly_reports.py

目的:
- before / after の anomaly report JSON を比較する
- reports/latest_ab_comparison.json を出力する
- reports/latest_ab_comparison.md を出力する

CLI:

python tools/compare_anomaly_reports.py \
  --before reports/baseline/latest_anomaly_report.json \
  --after reports/candidate/latest_anomaly_report.json \
  --output reports

任意:

python tools/compare_anomaly_reports.py \
  --before reports/baseline/latest_anomaly_report.json \
  --after reports/candidate/latest_anomaly_report.json \
  --output reports \
  --min-games 20

実装条件:
- 欠損キーは0として扱う
- before / after の各summaryを比較する
- metricごとに improved / worsened / unchanged を出す
- accept / reject / needs_more_games / human_review のdecisionを出す
- JSONとMarkdownの両方を出す
- テストしやすいように純粋関数を分ける

変更禁止:
- deck.csv は変更しない
- policy.py は変更しない
- strategy_engine.py は変更しない
- agent本体の行動ロジックは変更しない
- シミュレーション実行までは行わない
- LLM APIは呼ばない
- 自動mergeしない

完了条件:
- python tools/compare_anomaly_reports.py --help が通る
- サンプルJSONで latest_ab_comparison.json / md が生成される
- 既存の診断パイプラインと衝突しない
```

---

## Acceptance Criteria for This Instruction File

このmd追加PRの完了条件:

```text
- docs/instructions/20260619_pdca_self_learning_loop.md が追加されている
- documentation-only の変更である
- deck.csv は変更されていない
- policy.py は変更されていない
- strategy_engine.py は変更されていない
- Claude CodeがMVP Phase 1を実装できる粒度で書かれている
- 自動修正・自動採用・自動mergeを禁止している
```

---

## Recommended PR Summary

```text
- Add Claude Code instruction for a semi-automated PDCA/self-learning-style loop.
- Define how to compare before/after anomaly reports and produce adoption decisions.
- Keep this documentation-only and explicitly avoid automatic policy/deck/agent changes.
```
