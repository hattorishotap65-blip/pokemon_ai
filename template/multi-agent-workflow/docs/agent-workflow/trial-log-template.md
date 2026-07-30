# Trial log template

design-only trial（設計専用トライアル）または small implementation trial（小規模実装トライアル）の実施記録を残すための空の記入骨組みである。実際の記録はここに記入し、ファイル名を変更するかコピーして使うこと（例: `design-only-trial.md`、`small-implementation-trial.md`）。

## Scope

（このトライアルで扱う対象範囲・実案件の概要を記入する）

## Out of scope

（このトライアルで扱わない対象を記入する）

## Git state

- worktree:（記入欄）
- branch:（記入欄）
- base commit:（記入欄）
- 開始時 `git status --short`:（記入欄。空であることを確認してから開始する）

## Roles executed

（実際に起動したロール・エージェント・Codexスレッドを記入する。実行していないロールを`invoked`と記載しない。例: requirements-auditor、claude-architect、Independent Architect (codex)、simplifier、Red Team Reviewer (codex)、design-judge）

## Confirmed

（コード・設定・コマンド結果で確認済みの事実を記入する。ファイルパス・行番号・実行コマンドを付ける）

## Inference

（Confirmedな事実からの推論を記入する）

## Unknown

（現時点で確認できない事項を記入する。埋めずに明示すること）

## Evidence limitation

（レビュー・設計ロールがリポジトリの一次証拠を再確認できなかった場合、その事実と影響範囲を記入する。なければ「なし」と明記する）

## Verification

（実施した確認コマンド・確認手順とその結果を記入する。実行していないテスト・確認を「成功」と記載しない）

## User approval items

（このトライアルの結果として、ユーザーが承認すべき事項を記入する）

## Repository files changed

（このトライアルによって変更されたファイルの一覧を記入する。design-onlyトライアルであれば「なし」と明記する）

## Implementation performed

（このトライアルの中で実装を行ったかどうかを明記する。design-only/read-onlyトライアルであれば「no」と明記する）
