# Placeholders

このパッケージ内の文書・ファイル名に含まれる `{{...}}` 形式のプレースホルダーの一覧である。必要最小限に絞っており、これ以外のプレースホルダーは意図的に追加していない。

ユーザー名を含む絶対パスは、いずれの項目の「例」にも記載しない。

各項目の「未解決時に検証で失敗すべきか」は、同梱の検証CLI（verifier、`tools/verify_workflow_template.py`）の `plan` サブコマンドが実際に採用する方針である。未解決のプレースホルダーは `UNRESOLVED_PLACEHOLDER` 状態として報告され、exit code 1（人の対応が必要）となる。

**値の非開示に関する注意**: `target_path` を構成しないプレースホルダー（ファイル本文専用。下表参照）に渡した値は、verifierの標準出力へ一切表示されない。`target_path` を構成するプレースホルダー（`{{DESIGN_SKILL_NAME}}`・`{{ADR_NUMBER}}`）に渡した値は、レンダリング後の相対target pathの一部として表示され得る。いずれの場合も、APIキー・トークン・パスワード・個人情報等の秘密情報をプレースホルダーへ渡してはならない。target rootの絶対パスは常に `<target-root>` と表記され、実際の絶対パスは表示されない。

## `{{PROJECT_NAME}}`

| 項目 | 内容 |
|---|---|
| 意味 | 導入先プロジェクトの人間向け名称 |
| 必須/任意 | 必須 |
| 例 | `MyProject`（実在のプロジェクト名の具体例は記載しない） |
| 使用ファイル | `docs/agent-workflow/git-safety.md`、`docs/agent-workflow/README.md`、`docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md` |
| 未解決時に検証で失敗すべきか | はい。生成物に `{{PROJECT_NAME}}` の文字列がそのまま残っている場合は失敗として扱う |

## `{{DEFAULT_BRANCH}}`

| 項目 | 内容 |
|---|---|
| 意味 | 導入先プロジェクトの既定ブランチ名 |
| 必須/任意 | 必須 |
| 例 | `main` |
| 使用ファイル | `docs/agent-workflow/git-safety.md`、`docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md` |
| 未解決時に検証で失敗すべきか | はい |

## `{{MCP_SERVER_NAME}}`

| 項目 | 内容 |
|---|---|
| 意味 | Codex MCPサーバーの、`.mcp.json` 内でのエントリ名 |
| 必須/任意 | 必須（既定値あり） |
| 例 | `codex-reviewer`（このパッケージに同梱された `.mcp.json` は、この既定値をそのまま使用している） |
| 使用ファイル | `docs/agent-workflow/mcp-connection.md`、`docs/agent-workflow/multi-agent-design-skill.md`、`docs/agent-workflow/troubleshooting.md` |
| 未解決時に検証で失敗すべきか | はい。同梱の `.mcp.json` のサーバー名を変更しない場合も、文書側のプレースホルダーは既定値（`codex-reviewer`）へ明示的に置き換える必要がある |

## `{{CODEX_COMMAND}}`

| 項目 | 内容 |
|---|---|
| 意味 | Codex MCPサーバーを起動するCLIコマンド名 |
| 必須/任意 | 必須（既定値あり） |
| 例 | `codex`（同梱の `.mcp.json` はこの既定値をそのまま使用している） |
| 使用ファイル | `docs/agent-workflow/mcp-connection.md`、`docs/agent-workflow/troubleshooting.md` |
| 未解決時に検証で失敗すべきか | はい |

## `{{DESIGN_SKILL_NAME}}`

| 項目 | 内容 |
|---|---|
| 意味 | design-only Skillのディレクトリ名・スラッシュコマンド名 |
| 必須/任意 | 必須（既定値あり） |
| 例 | `multi-agent-design` |
| 使用ファイル | `.claude/skills/{{DESIGN_SKILL_NAME}}/SKILL.md`（ディレクトリ名そのもの）、`README.md`（パッケージ直下）、`docs/agent-workflow/multi-agent-design-skill.md`、`docs/agent-workflow/quality-first-token-policy.md`、`docs/agent-workflow/subagents.md`、`docs/agent-workflow/troubleshooting.md`、`docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md` |
| 未解決時に検証で失敗すべきか | はい。ディレクトリ名として `{{DESIGN_SKILL_NAME}}` が残っている場合、Skillとして機能しないため必ず失敗として扱う |

## `{{ADR_NUMBER}}`

| 項目 | 内容 |
|---|---|
| 意味 | 導入先プロジェクトの意思決定記録（ADR）連番のうち、このワークフロー境界の記録に割り当てる番号 |
| 必須/任意 | 必須 |
| 例 | `0001` |
| 使用ファイル | `docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md`（ファイル名そのもの）、`.claude/skills/{{DESIGN_SKILL_NAME}}/SKILL.md`、`README.md`（パッケージ直下）、`docs/agent-workflow/README.md`、`docs/agent-workflow/subagents.md`、`PROJECT_RULES_SNIPPET.md` |
| 未解決時に検証で失敗すべきか | はい |

## `{{TEST_COMMANDS}}`

| 項目 | 内容 |
|---|---|
| 意味 | 導入先プロジェクト自身の検証・テストコマンド |
| 必須/任意 | 必須（ただし「未定義」であることを明示する値も有効な解決とする） |
| 例 | `pytest` / `未定義（今後追加予定）` |
| 使用ファイル | `docs/agent-workflow/review-protocol.md` |
| 未解決時に検証で失敗すべきか | プレースホルダーの文字列がそのまま残っている場合のみ失敗とする。「未定義」等の明示的な記述に置き換えられていれば失敗としない |

## `{{PROTECTED_PATHS}}`

| 項目 | 内容 |
|---|---|
| 意味 | 導入先プロジェクトで、変更に特に注意が必要なファイル・パスの一覧（提出物、本番設定など） |
| 必須/任意 | 必須（ただし「該当なし」であることを明示する値も有効な解決とする） |
| 例 | `main.py, config/production.yaml` / `該当なし` |
| 使用ファイル | `docs/agent-workflow/review-protocol.md` |
| 未解決時に検証で失敗すべきか | プレースホルダーの文字列がそのまま残っている場合のみ失敗とする。「該当なし」等の明示的な記述に置き換えられていれば失敗としない |

## `{{PROJECT_SPECIFIC_DOCS}}`

| 項目 | 内容 |
|---|---|
| 意味 | 導入先プロジェクト固有の戦略・性能・引き継ぎ文書等へのポインタ |
| 必須/任意 | 必須（ただし「該当なし」であることを明示する値も有効な解決とする） |
| 例 | `docs/architecture-notes.md` / `該当なし` |
| 使用ファイル | `docs/agent-workflow/README.md`、`docs/decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md` |
| 未解決時に検証で失敗すべきか | プレースホルダーの文字列がそのまま残っている場合のみ失敗とする。「該当なし」等の明示的な記述に置き換えられていれば失敗としない |

## 備考

- `.claude/agents/*.md` 内の `model:` エイリアス（`haiku` / `sonnet` / `opus`）はプレースホルダーではない。すでに汎用的なエイリアスであるため、そのまま使用する
- `.mcp.json` はverbatimコピーであり、プレースホルダーを含まない。`{{MCP_SERVER_NAME}}` / `{{CODEX_COMMAND}}` の既定値は、この同梱ファイルの実際の値と一致させている
