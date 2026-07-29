# Design-only trial

## Step 7の目的

Step 7は、Step 1〜6で整備したマルチエージェントワークフロー（論理ロール、Claude project subagents、Codex MCP接続、`multi-agent-design` Skill）を、架空のタスクではなく**実案件**を使って一度通しで動かし、Skillが実際に設計専用・read-onlyのまま最後まで動作するかを確認することである。Step 7Aでこの試行のためのクリーンなworktreeを準備し、Step 7Bで実行結果を文書化した。

## 実施日

2026-07-30

## 実行環境

- worktree: `C:\Users\shclo\projects\pokemon_ai_step7`
- branch: `agent/step7-design-only-trial`（`origin/main`、PR #207マージ後の状態から作成）
- Terminal版Claude Code

## 使用Skill

`multi-agent-design`（[`../../.claude/skills/multi-agent-design/SKILL.md`](../../.claude/skills/multi-agent-design/SKILL.md)、Step 6）を `/multi-agent-design` で明示的に起動した。

## 実案件の概要

**開発元ファイルとルート提出用ファイルの不一致を防ぐための、安全な同期・差分検証ワークフローの設計。**

対象として確認した主なファイル・ディレクトリ:

- `experiments/agents/raging_bolt/`
- `experiments/decks/raging_bolt_ogerpon.csv`
- `main.py`
- `deck.csv`
- `params.json`
- `build_submission.py`
- `CLAUDE.md`
- `AGENTS.md`
- `experiments/agents/raging_bolt/HANDOFF.md`
- `reference/extracted/cg/`
- `tools/`
- `data/`

今回は設計のみであり、これらのファイルの同期・実装・編集は一切行っていない。

## 変更禁止範囲

Skill自体の定義（`.mcp.json`、`.claude/agents/`、`.claude/skills/`）、`CLAUDE.md`/`AGENTS.md`、`experiments/`、`tools/`、`reference/`、`data/`、`build_submission.py`、`main.py`、`deck.csv`、`params.json`、`submission.tar.gz`、テスト、CI。Step 7Bで変更可能なのは本文書と `README.md`・ADRの3件のみ。

## 受入条件

Skillが8フェーズ（Phase 0〜Phase 7）を規定通り遷移し、`READY_FOR_APPROVAL` に到達した場合でも実装を開始せず、ユーザーへ明示的に承認を求めて停止すること。実行前後でリポジトリに一切のファイル変更が生じないこと。

## Phase 0〜Phase 7の実行結果

### Phase 0 — Preflight and safety gate

クリーンなStep 7 worktree（branch: `agent/step7-design-only-trial`）で開始した。`git status --short` は空だった。`codex-reviewer` MCPサーバーの利用可否と4つのproject subagentsの利用可否を確認し、設計専用・read-onlyであることを確認した。

### Phase 1 — Requirements audit

`requirements-auditor` を明示的に起動した。`Status: READY`。Task ID: `TASK-SYNCDESIGN-20260730`。Evidence Registryを作成した。不明事項を勝手に補完しなかった。

### Phase 2 — Independent architecture proposals

`claude-architect` を明示的に起動した。Codex Independent Architectを新規read-onlyスレッドで起動した。両者は互いの初期案を見ない状態で独立に完成させ、両案が完成してから次フェーズへ進んだ。

### Phase 3 — Simplification and Red Team review

`simplifier` を実行した。Codex Red Team Reviewerを新規read-onlyスレッドで実行した。過剰設計、誤上書き、データ損失、TOCTOU、パス封じ込め、バックアップ、deck検証、クロスプラットフォームの観点等を確認した。

### Phase 4 — Evidence-based rebuttal rounds

Codex側のrebuttalは、Independent Architectの既存threadを `codex-reply` で継続し、新しいthreadは作らなかった。Claude側は親Orchestratorが元Proposal IDとEvidence Registryに基づき応答を構成した。rebuttalは1ラウンドのみ実施した。Round 2は、Round 1後に重大な未解決対立が残らなかったため実施しなかった。

### Alternative Architect（未実施）

起動しなかった。理由: 両案がREJECT相当ではなく、Round 1後に重大な未解決対立がなく、ユーザーが第3案を要求していなかったため。起動しなかった理由はExecution Traceへ記録した。

### Phase 5・6 — Anonymization / Anonymous judging and integrated design

案A・案Bとして匿名化した上で `design-judge` を起動した。design-judgeは判断に重要な事実をRead/Glob/Grepでリポジトリに対して自ら再確認した。

匿名採点:

| 案 | 点数 |
|---|---:|
| 案A | 81 |
| 案B | 69 |

Verdict: `READY_FOR_APPROVAL`

### Phase 7 — User approval gate

`READY_FOR_APPROVAL` を実装許可として扱わなかった。実装承認をユーザーへ明示的に求めて停止した。ユーザーは実装を承認していない。Step 8は開始していない。

## Design Judgeが発見した重要事項（確認済み事実）

design-judgeによる一次証拠の再確認で、以下が確認済み事実として判明した。今回はいずれも修正していない。Step 7では発見と設計上の扱いを記録するのみである。

- `main.py` の開発元（`experiments/agents/raging_bolt/`）とルート版には大きな差分があり、telemetry関連の差分をpromoteすべきかstripすべきかは未決定
- `deck.csv` の正本候補は単純な2ファイルではない: ルートの `deck.csv`、`experiments/decks/raging_bolt_ogerpon.csv`、`tools/deck_builder.py` が生成するルート `deck.csv`、`data/deck.csv` という古い別形式のファイル、の4系統が存在する
- `params.json` と `deck.csv` は現時点で一致していると報告されたが、将来の不一致時にどちらを正本とするかは未決定
- `reference/extracted/cg/api.py` 上の `CardData` には `regulation` フィールドが存在せず、`CLAUDE.md` の記述と実装に不一致がある
- Windows環境では `libcg.so` のみが存在し `cg.dll` が存在しないため、`cg.api` を前提にした検証設計はWindows開発環境では利用できない可能性がある
- `build_submission.py` は必須ファイルが欠落してもエラー終了せず、不完全なtarを作成し得る可能性が設計中に指摘された
- 既存テストは `experiments/` 配下に置くリポジトリ慣行が確認された

## 統合設計の概要

**この統合設計は未承認・未実装であり、Step 8の候補であって採用決定ではない。**

Design Judgeは、将来の小規模実装候補として read-only check-only v1 を提示した。

### Target files候補

- `tools/submission_sync.py`
- `experiments/test_submission_sync.py`
- `CLAUDE.md` への追記
- `AGENTS.md` への追記
- `experiments/agents/raging_bolt/HANDOFF.md` へのポインタ追加

### v1の重要な境界（候補案の内容であり、確定仕様ではない）

- apply機能なし
- 書き込みなし
- 同期実行なし
- `cg` importなし
- stdlibのみ
- 差分を `BYTE_IDENTICAL` / `SEMANTICALLY_EQUIVALENT` / `DIFFERENT` の3状態で分類
- `build_submission.py` とは独立し、`build_submission.py` を呼ばない・`build_submission.py` から呼ばれない
- CLIの存在はタスク単位の変更承認を代替しない
- root外やsymlink/reparse pointへのパス逸脱を拒否
- テストは実ファイルへ書き込まない

## Risks

- 正本が未確定なまま同期ツールを実装すると、誤った方向へ「同期」してしまうリスクがある
- `CLAUDE.md` の `regulation`/`AreaType` 関連の記述と実装の不一致を放置すると、将来の開発判断を誤らせるリスクがある
- Windows環境で `cg` importを前提にした設計を進めると、開発環境で検証できないリスクがある
- `build_submission.py` の欠落時無エラーの挙動が、提出物の欠陥を見逃すリスクにつながる可能性がある

## Unknown / User approval items

以下はStep 8着手前のユーザー承認事項、またはUnknownとして記録する。今回いずれも決定済みではない。

- `deck.csv` の正本をどれにするか
- `main.py` 差分のpromote/strip方針
- `params.json` の正本
- EOLのみ異なる場合のstrict動作をどうするか
- `main.py`/`deck.csv`/`params.json` の3ファイルを1リリース単位として扱うか
- 開発版 `main.py` を直接実行する運用の有無
- `CLAUDE.md` の `regulation` 記述の修正要否
- `CLAUDE.md` の `AreaType` 表の修正要否
- 将来apply機能を設計するか
- `build_submission.py` の欠落時動作を別タスクで修正するか

## Execution Trace

```
- requirements-auditor: invoked / READY
- claude-architect: invoked / proposal received
- Independent Architect (codex): invoked / proposal received
- simplifier: invoked
- Red Team Reviewer (codex): invoked
- codex-reply: same thread reused / yes
- rebuttal rounds: 1
- Alternative Architect: not invoked / trigger absent
- design-judge: invoked / READY_FOR_APPROVAL
- repository files changed: no
- implementation performed: no
```

## read-only確認・Git確認結果

Skill実行終了後、外側のGit Bashで以下を確認し、いずれも空だった。

- `git status --short`
- `git diff --check`
- `git diff --name-only`
- `git ls-files --others --exclude-standard`

ファイルの作成・編集・削除は一切なく、commit・push・PRも行っていない。

## Invalid tool parametersの観測

Round 2要否判断付近で、1回 `Invalid tool parameters` が表示された。ただしその後、親セッションがRound 2不要と判断して正常にPhase 5・6へ進み、Design Judgeの結果と最終Execution Traceを出力した。この事象によるリポジトリ変更や誤った成功報告はなかった。原因は確認できていないため、Skillのバグと断定はしない。

## /loop wakeupによる重複応答

Phase 7完了後、外部の `/loop wakeup` により完了済みタスクへの短い重複応答が発生した。新しい設計処理・ツール呼び出し・ファイル変更は行われなかった。これはClaude Codeセッションレベルの挙動として記録し、Skill自体のフェーズ再実行成功とは扱わない。原因は未確認のため、修正済みとは記載しない。

## Agent ID / threadIdの記録について

実行時のAgent ID、threadId、MCP task IDはいずれも記録していない。

## 検証状態

**Verified**

実案件を用いた `/multi-agent-design` の実機トライアルにより、8フェーズ（Phase 0〜Phase 7）が規定通り遷移し、設計専用・read-onlyの境界とユーザー承認前の停止が実際に機能することを確認した。

## Step 8は未実施

Design Judgeが提示した read-only check-only v1 は未承認・未実装の候補であり、Step 8（小規模実装トライアル）は開始していない。
