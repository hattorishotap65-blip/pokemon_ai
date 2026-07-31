# Repository audit template

このワークフローを導入する前に、対象リポジトリの現状を監査するための空の記入骨組みである。実際の監査結果はここに記入し、ファイル名を変更するかコピーして使うこと（例: `step1-repository-audit.md`）。

## Scope

（この監査で確認する対象範囲を記入する）

## Out of scope

（この監査で確認しない対象を記入する）

## Git state

- 現在のブランチ:（記入欄）
- `git status --short` の結果:（記入欄）
- 直近のcommit:（記入欄）
- 入れ子のGitリポジトリの有無:（記入欄）

## Confirmed

（コード・設定・コマンド結果で確認済みの事実を記入する。ファイルパス・行番号・実行コマンドを付ける）

## Inference

（Confirmedな事実からの推論を記入する）

## Unknown

（現時点で確認できない事項を記入する。埋めずに明示すること）

## Evidence limitation

（一次証拠を確認できなかった箇所があれば、その範囲と理由を記入する。なければ「なし」と明記する）

## Roles executed

（この監査で実際に起動したロール・ツールを記入する。実行していないロールを記入しない）

## Verification

（実施した確認コマンド・確認手順とその結果を記入する。実行していない確認を「成功」と記載しない）

## User approval items

（この監査の結果を踏まえて、ユーザーが承認すべき事項を記入する）

## Repository files changed

（この監査によって変更されたファイルの一覧を記入する。監査がread-onlyであれば「なし」と明記する）

## Implementation performed

（この監査の中で実装を行ったかどうかを明記する。design-only/read-onlyの監査であれば「no」と明記する）
