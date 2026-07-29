# マルチエージェント開発ワークフロー

Claude CodeとCodexを併用してこのリポジトリを開発するための、共通ワークフロー文書の入口。

このディレクトリの文書は**役割分担・進め方・レビュー手順**だけを扱う。アプリケーションの性能改善案やデッキ戦略は複製しない（それらは `experiments/agents/raging_bolt/HANDOFF.md` や `docs/pokemon_ai_performance_improvement_memo_v4_1.md` 等の既存文書を参照）。

## 目的

- Claude CodeとCodexを、役割を分離して利用する
- 独立した設計案を比較する
- 1つのモデルの思い込みで実装しない
- 実装前に安全性、根拠、テスト可能性を確認する
- ユーザーが明示したStepだけを実施する

## 適用範囲

### 使用するケース

- 複数ファイルにまたがる設計
- アーキテクチャ変更
- 性能改善
- リファクタリング
- 新機能の設計
- 高リスクなバグ修正
- テスト戦略の設計

### 原則として使用しないケース

- 誤字修正
- 単純な文書修正
- 変更内容が一意な小規模修正
- ユーザーが単独エージェント作業を指定した場合

## 論理的な役割

役割は**モデル名と混同しない**。同じ論理ロールを異なるモデルが担うことも、将来変わることもある。

| 論理ロール | 役割の内容 |
|---|---|
| Orchestrator / Main Architect / Implementation Owner | タスク全体の進行管理、独立した主設計案の作成（他の設計案を見る前）、承認された統合設計の実装 |
| Requirements Auditor | タスク入力の過不足・曖昧さの監査（read-only） |
| Simplifier | 過剰な複雑さ・不要な変更範囲の指摘（read-only） |
| Independent Architect | 独立した実務的設計案の作成、Main Architectの案を見る前（read-only） |
| Alternative Architect | 重大な対立・追加案が必要な場合・またはユーザー指定時のみ、追加の独立設計案を作成（read-only） |
| Red Team Reviewer | 各設計案の弱点・リスクの指摘（read-only） |
| Design Judge / Integrator | 匿名評価、採用・不採用理由の判定、複数案の統合設計作成、未解決事項とユーザー承認事項の整理（read-only） |
| Final Auditor | 実装後の統合設計との一致・副作用の監査（read-only、コード修正はしない） |

通常時は、Main Architect（Sonnet）の主設計案と Independent Architect（Codex Terra）の独立設計案の**最低2案**を比較する。Alternative Architect は重大な対立・追加案が必要な場合・またはユーザーが指定した場合にのみ追加する（使用しない場合も2案比較は実施する）。

## 現在の希望割り当て

以下は現時点での**運用上の希望ラベル・役割割り当て**であり、MCPやCLIで実際に確認された接続名・モデルIDではない。実モデルIDの確認はStep 4以降にローカル環境で行い、確認できていないIDを設定へハードコードしない。

| 希望ラベル | 割り当てる論理ロール | 権限 |
|---|---|---|
| Claude Sonnet 5 | Orchestrator / Main Architect / Implementation Owner | 編集可 |
| Claude Haiku 4.5 | Requirements Auditor、Simplifier | read-only |
| Claude Opus 5 | Design Judge / Integrator | read-only |
| Codex Terra High | Independent Architect | read-only |
| Codex GPT-5.5 High | Alternative Architect（重大な対立・追加案が必要な場合・またはユーザー指定時のみ使用） | read-only |
| Codex GPT-5.4 High | Red Team Reviewer | read-only |
| Codex Sol Extra High | Final Auditor | read-only |

Sonnet は「統合設計の作成」担当ではない。統合設計は Design Judge / Integrator（Opus）が匿名評価結果を基に作成し、ユーザーが承認したものを Sonnet が実装する。

## 基本フロー

1. タスク受付
2. 変更範囲と禁止範囲の確定
3. 要件監査
4. 独立した設計案の作成
5. 相互レビュー
6. Red Teamレビュー
7. 最大2ラウンドの反論・修正
8. 匿名評価
9. 統合設計
10. ユーザー承認
11. Sonnetだけが実装
12. テスト
13. Codex最終監査
14. ユーザーによるマージ判断

具体的な手順・入力フォーマット・証拠区分・停止条件は [`review-protocol.md`](review-protocol.md) を参照。この方式を採用した背景・境界線の決定記録は [`../decisions/0001-multi-agent-workflow-boundary.md`](../decisions/0001-multi-agent-workflow-boundary.md) を参照。

## 導入状況

Step 4のCodex MCP接続（プロジェクトスコープの `.mcp.json`、サーバー名 `codex-reviewer`）を追加し、`codex`・`codex-reply` ツールの実機での読み取り専用呼び出しを確認済み。詳細は [`mcp-connection.md`](mcp-connection.md) を参照。Step 5のClaude project subagents（`requirements-auditor` / `simplifier` / `claude-architect` / `design-judge`）も追加済みで、Agentツールによる明示的な直接起動での実機確認を完了している。詳細は [`subagents.md`](subagents.md) を参照。Step 6のmulti-agent-design Skill（`.claude/skills/multi-agent-design/SKILL.md`）も追加済みで、ユーザーの明示起動による8フェーズ実行の実機確認を完了している。詳細は [`multi-agent-design-skill.md`](multi-agent-design-skill.md) を参照。Step 7以降は未実施。

## 関連文書

- [mcp-connection.md](mcp-connection.md) — Codex MCP接続設定と接続確認結果（Step 4）
- [subagents.md](subagents.md) — Claude Code project subagentsの定義と実機確認結果（Step 5）
- [multi-agent-design-skill.md](multi-agent-design-skill.md) — read-only multi-agent design Skillの定義と実機確認結果（Step 6）
- [quality-first-token-policy.md](quality-first-token-policy.md) — 判断品質を維持しながら重複コンテキストを削減する共通方針
- [review-protocol.md](review-protocol.md) — 設計討論・レビューの具体的手順
- [../decisions/0001-multi-agent-workflow-boundary.md](../decisions/0001-multi-agent-workflow-boundary.md) — この方式の意思決定記録（ADR）
- [step1_repository_audit.md](step1_repository_audit.md) — 導入前のリポジトリ現状監査（Step 1）
- [../../CLAUDE.md](../../CLAUDE.md) — Claude Code向けプロジェクトルール
- [../../AGENTS.md](../../AGENTS.md) — Codex向けプロジェクトルール
