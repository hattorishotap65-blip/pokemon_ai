# Codex MCP connection

## 目的

Claude Codeから、ログイン済みのCodex CLIをMCPサーバーとして呼び出せるようにする。[`README.md`](README.md) / [`review-protocol.md`](review-protocol.md) で定義した Independent Architect（Codex Terra）・Alternative Architect・Red Team Reviewer・Final Auditor の各論理ロールを、実際にCodex CLI経由で呼び出すための接続設定（Step 4A）。この文書はStep 4Aの接続設定のみを扱い、Step 5以降（Claude subagents、multi-agent-design Skill）は対象外。

## 接続設定

| 項目 | 内容 |
|---|---|
| MCPサーバー名 | `codex-reviewer` |
| 起動コマンド | `codex mcp-server` |
| 設定スコープ | `project` |
| 設定ファイル | [`../../.mcp.json`](../../.mcp.json) |

`.mcp.json` は `claude mcp add --scope project codex-reviewer -- codex mcp-server`（Claude Code公式CLI）で生成した。生成後、`codex-reviewer` エントリへ `"alwaysLoad": true` を手動で追加している（他のキーは公式CLI生成のまま変更していない）。

## セキュリティ・運用方針

- 認証情報（APIキー、トークン等）をリポジトリへ保存しない
- OpenAI API・Anthropic APIのAPIキー課金利用を前提にしない。ログイン済みのCodex CLI（ChatGPT Plus）とClaude Codeのサブスクリプション枠を使用する
- 個人固有の絶対パス（Windowsユーザーディレクトリ、WSLホームパス等）を設定へ記載しない
- モデルIDをハードコードしない。今回の接続確認では model override を指定せず、Codex CLIの現在のデフォルトモデルを使用する
- `cwd` / `sandbox` / `approval-policy` / reasoning effort の固定値は設定へ記載しない。これらは実際のMCPツール呼び出しごとに指定する想定

## 接続確認環境

| ツール | バージョン |
|---|---|
| `codex` (codex-cli) | 0.146.0 |
| `claude` (Claude Code) | 2.1.220 |

確認シェル: Claude Code自体が動作しているGit Bash（Windowsネイティブ環境。`command -v codex` / `command -v claude` の両方が同一環境で解決することを確認済み）。

## 期待されるMCPツール

- `codex`
- `codex-reply`

## 手動確認手順

1. Claude Code を再起動する（`.mcp.json` の変更を反映させるため）
2. プロジェクトスコープのMCPサーバー承認プロンプトが表示された場合、内容を確認した上でユーザーが承認する
3. `claude mcp list` で `codex-reviewer` が `Connected` 相当の状態になっていることを確認する
4. `claude mcp get codex-reviewer` で接続詳細を確認する
5. 実際に `codex` / `codex-reply` ツールを呼び出し、応答が得られることを確認する

## 検証結果

手動接続確認をユーザーが実施し、以下を確認した。

- Claude Code内の `/mcp` で `codex-reviewer` が `connected`、2 tools（`codex`、`codex-reply`）と表示された
- `codex` ツールを read-only sandbox、`approval-policy: never` で呼び出せた
- `CLAUDE.md` と `docs/agent-workflow/README.md` を読み取れた
- model override は指定していない（Codex CLIの現在のデフォルトモデルを使用）
- 継続用の thread ID が返され、`codex-reply` で同一スレッドを継続できた（thread ID自体は一時的な実行識別子のため本文書には記録しない）
- ツール呼び出し前後で取得した2回の `git status --short` は完全に一致した
- MCPツール呼び出しによるファイル変更は発生しなかった

## 検証状態

**Verified**

上記の手動接続確認により、`codex-reviewer` 経由での読み取り専用MCPツール呼び出しが実際に成功することを確認した。

## 今後の範囲外（Step 5以降）

Claude subagents の定義、multi-agent-design Skill の追加は、本Step 4Aの範囲外であり未実施。
