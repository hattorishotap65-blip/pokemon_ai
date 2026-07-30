# Codex MCP connection

## 目的

Claude Codeから、ログイン済みのCodex CLIをMCPサーバーとして呼び出せるようにする。[`README.md`](README.md) / [`review-protocol.md`](review-protocol.md) で定義した Independent Architect・Alternative Architect・Red Team Reviewer・Final Auditor の各論理ロールを、実際にCodex CLI経由で呼び出すための接続設定。この文書はCodex MCP接続設定と、導入先プロジェクトでの実機検証結果を記録するための文書である。

## 接続設定

| 項目 | 内容 |
|---|---|
| MCPサーバー名 | `{{MCP_SERVER_NAME}}` |
| 起動コマンド | `{{CODEX_COMMAND}} mcp-server` |
| 設定スコープ | `project` |
| 設定ファイル | [`../../.mcp.json`](../../.mcp.json) |

`.mcp.json` は `claude mcp add --scope project {{MCP_SERVER_NAME}} -- {{CODEX_COMMAND}} mcp-server`（Claude Code公式CLI）で生成できる。このテンプレートに同梱している `.mcp.json` は、`{{MCP_SERVER_NAME}}` の既定値として `codex-reviewer` を、`{{CODEX_COMMAND}}` の既定値として `codex` をそのまま使用している。サーバー名・起動コマンドを変更する場合は、同梱の `.mcp.json` と、このファイルを含む全文書のプレースホルダーの両方を一致させること。

## セキュリティ・運用方針

- 認証情報（APIキー、トークン等）をリポジトリへ保存しない
- 特定の有料API課金利用を前提にしない。ログイン済みのCodex CLIとClaude Codeの既存契約枠を使用する
- 個人固有の絶対パス（ユーザーディレクトリ、ホームパス等）を設定へ記載しない
- モデルIDをハードコードしない。接続確認では model override を指定せず、Codex CLIの現在のデフォルトモデルを使用する
- `cwd` / `sandbox` / `approval-policy` / reasoning effort の固定値は設定へ記載しない。これらは実際のMCPツール呼び出しごとに指定する想定

## 接続確認環境

導入先プロジェクトで実際に確認した `codex` (codex-cli) と `claude` (Claude Code) のバージョン、確認シェル（Windows Git Bash / PowerShell / Linux・macOSシェル等）は、導入時にこの節へ記入すること。

（記入欄 — 未記入の場合は、接続確認がまだ行われていないことを意味する）

## 期待されるMCPツール

- `codex`
- `codex-reply`

## 手動確認手順

セッション外から実行する `claude mcp list` / `claude mcp get` の表示と、実際に動作しているClaude Codeセッション内部の接続状態が食い違う場合がある。そのため、確認の主手段はセッション内の `/mcp` とし、`claude mcp list` / `get` は補助的な診断としてのみ使う。

1. Claude Code を再起動する（`.mcp.json` の変更を反映させるため）
2. プロジェクトスコープのMCPサーバー承認プロンプトが表示された場合、内容を確認した上でユーザーが承認する
3. リポジトリルートからClaude Codeを起動する
4. 同じClaude Codeセッション内で `/mcp` を開く
5. `{{MCP_SERVER_NAME}}` が `connected`・2 tools であることを確認する
6. 同じセッションのまま `codex` / `codex-reply` を呼び出す
7. `claude mcp list` / `get` は補助的な診断に使用する

## 検証結果

導入先プロジェクトでの実機確認結果は、この節へ記入すること。

- `/mcp` での接続状態確認結果:（記入欄）
- read-only sandbox・`approval-policy: never` での `codex` ツール呼び出し結果:（記入欄）
- `codex-reply` によるスレッド継続確認結果:（記入欄）
- ツール呼び出し前後の `git status --short` の一致確認:（記入欄）
- ファイル変更の有無:（記入欄）

## 検証状態

（記入欄 — `Verified` / `Not yet verified` / `Partially verified` のいずれかと、その根拠を記入する。実行していない確認を `Verified` と記載しない）

## 対象外

Claude subagents の定義、design-only Skill の追加は、本文書の対象外である。それぞれ [`subagents.md`](subagents.md) / [`multi-agent-design-skill.md`](multi-agent-design-skill.md) を参照。
