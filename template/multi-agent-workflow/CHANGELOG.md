# Changelog

このファイルは `template/multi-agent-workflow/` パッケージ自体のバージョン履歴を記録する。パッケージを導入したプロジェクト側の変更履歴ではない。

## 0.2.0

- 汎用Outcome Improvement Cycleとversioned App Profile v1契約を追加した。
- 2案固定、Falsification、順序反転Blind Judge、Selected Design Refinement最大1回、Alignment/Test/Final Audit、screening/confirmationの有限フローを追加した。
- Python標準ライブラリだけのread-only `outcome_gatekeeper.py`を追加した。Profile文字列のcommand実行、外部評価実行、network、Git、ファイル書込みは行わない。
- Pokemon AIとRAGの`example_only` Profileを追加した。例示値は実運用defaultではなく、evaluateはfail-closedでBLOCKEDになる。
- 既存`multi-agent-design` Skillと`verify_workflow_template.py`は変更せず、design-only責務とtemplate-integrity責務を維持した。
- source repositoryでの導入とunittestを追加した。heterogeneous independent reviewとcross-OS portabilityは未完了である。

## 0.1.1

- package-localな `.gitattributes`（`* -text`）を追加し、`core.autocrlf=true` のWindows環境でのfresh checkoutでも、このパッケージ配下のファイルのワーキングツリーbytesがGit blobと一致するよう修正した。
- `manifest.json` に記録していた5件（`.mcp.json` および `.claude/agents/` の4ファイル）のSHA-256を、実際のGit blob（LF）のbytesを基準とした値へ訂正した。これら5ファイルの本文（Git blobの内容）は変更していない。
- verifierのstrict byte comparison（改行コードを正規化しない設計）は変更していない。
- 導入先リポジトリ側の改行コード方針の自動設定は、このバージョンの対象外である。

## 0.1.0

- reusable multi-agent workflow packageとして、`template/multi-agent-workflow/` 配下のテンプレート内容と静的 `manifest.json` を追加した。
- read-only verifier（`tools/verify_workflow_template.py`）を追加した。Python標準ライブラリのみを使用し、`subprocess` は一切importしない。コピー・apply・install・update・uninstall・merge等の書き込み系機能は持たない。
- `source-integrity` サブコマンドを追加した（パッケージ自身の内容を、manifestに登録されたSHA-256と照合する）。
- `plan` サブコマンド（導入先との比較。adoption plan）を追加した。プレースホルダー置換後のバイト内容を、指定した導入先の実ファイルと直接バイト比較する（`BYTE_IDENTICAL` / `BYTE_DIFFERENT`）。この比較にSHA-256は使用しない。書き込みは一切行わない。
- manifest inventory（`manifest.json`）に、各ファイルの分類・content_mode・SHA-256・adoption_mode・target_pathを記録した。
- プレースホルダー処理: `{{` と `}}` で囲まれた厳密なトークンのみを対象とし、宣言されていないトークンや未解決のトークンをINVALID/UNRESOLVED_PLACEHOLDERとして報告する。
- path containment検証: 絶対パス・`..` traversal・UNC path・drive-relative path・symlink/junction/reparse pointによるredirect等を拒否する。
- resource limits: manifestサイズ・files件数・1ファイルサイズ・合計読み取りサイズ・パス階層・プレースホルダー件数のそれぞれに上限を設け、超過をINVALIDとして報告する。
- unlisted package file検出: manifestに登録されていない通常ファイル・special fileを `source-integrity` が検出する。
- 対応するテストがsource repository側に追加され、`unittest` で検証されている。
- 実際のproduction repositoryへの本番導入実績は、このバージョンの時点ではまだない。disposable sample targetによる移植試験結果は本ファイル後半（「Disposable portability trialの実施と、その結果を反映した文書更新」）およびREADME.mdの「Portability validation」節を参照。
- commit・push・PR・mergeは本バージョンの作成範囲に含まれない。

**既知の制限（Unicode正規化）**: normalization-sensitiveなファイルシステムでは、Unicode正規化形式の違いがcase-collision判定へ影響する可能性がある。Windows/Linuxおよび現在の環境では未再現。自動修正・自動renameは行わない。

### Disposable portability trialの実施と、その結果を反映した文書更新

使い捨て（disposable）のsample targetを用いた、手動導入フロー・verifierの挙動に関する移植試験を実施し、その結果をREADME.md・本ファイル・troubleshooting.mdへ反映した（新機能・設計変更・コード実装の変更は行っていない）。

- disposable fresh non-Git target（Gitリポジトリではない空ディレクトリ）で手動導入フローと `plan` の挙動を検証した
- disposable existing dirty Git target（commit済みファイル＋未追跡ファイルを含む既存Gitリポジトリ）で手動導入フローと `plan` の挙動を検証した
- 既存のdirty/未追跡ファイルを `plan` が変更しないことを確認した
- 既存の `COPY_IF_ABSENT` 対象ファイルを自動上書きしないことを確認した
- `.mcp.json` のmanual mergeを検証した（既存server設定を保持したまま、operatorが新規entryを手動統合できることを確認した）
- strict byte comparison（プレースホルダー置換後の厳密なバイト一致判定）によるdrift検出・復旧確認を行った
- 手動コピー処理をtext modeで実装した場合のCRLF/LF変換リスクを確認した
- 上記を踏まえ、binary-safeな手動導入guidance（README.mdの「Binary-safe manual adoption」節）を追加した
- troubleshooting.mdへ、意図しない改行コード変換による誤ったDIFFERENT報告、およびmanual mergeがDIFFERENTのままになることについての項目を追加した

確認済み（1つのWindows環境）:

- disposable fresh non-Git target
- disposable existing dirty Git target
- 手動導入フロー（COPY_IF_ABSENT / MANUAL_REVIEW / TEMPLATE_RENAME / PACKAGE_METADATA / REFERENCE_ONLY）
- 既存ファイル保護（自動上書きしないこと）
- strict byte comparisonによる比較・drift検出

未確認:

- production repositoryへの本番導入
- cross-OS portability（Windows以外の環境）
- 導入先固有の組織ポリシーとの統合
- normalization-sensitiveなファイルシステムでの挙動
- semantic mergeの正しさ（`.mcp.json` 等の統合内容の意味的な妥当性）

将来のバージョンは [Semantic Versioning](https://semver.org/) に従う方針とする。バージョニング方針の詳細は `README.md` を参照。
