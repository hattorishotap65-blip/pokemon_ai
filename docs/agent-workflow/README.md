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
| Orchestrator / Implementation Owner | タスク全体の進行管理と、承認された統合設計の実装 |
| Requirements Auditor | タスク入力の過不足・曖昧さの監査（read-only） |
| Simplifier | 過剰な複雑さ・不要な変更範囲の指摘（read-only） |
| Independent Architect | 独立した設計案Aの作成（read-only） |
| Alternative Architect | 独立した設計案Bの作成、必要な場合のみ（read-only） |
| Red Team Reviewer | 各設計案の弱点・リスクの指摘（read-only） |
| Design Judge / Integrator | 匿名化された設計案の評価と統合設計の作成（read-only） |
| Final Auditor | 実装後の統合設計との一致・副作用の監査（read-only、コード修正はしない） |

## 現在の希望割り当て

以下は現時点での**運用上の希望ラベル・役割割り当て**であり、MCPやCLIで実際に確認された接続名・モデルIDではない。実モデルIDの確認はStep 4以降にローカル環境で行い、確認できていないIDを設定へハードコードしない。

| 希望ラベル | 割り当てる論理ロール | 権限 |
|---|---|---|
| Claude Sonnet 5 | Orchestrator / Implementation Owner、統合設計の作成、実装担当 | 編集可 |
| Claude Haiku 4.5 | Requirements Auditor、Simplifier | read-only |
| Claude Opus 5 | Design Judge、Integration Judge | read-only |
| Codex Terra High | Independent Architect | read-only |
| Codex GPT-5.5 High | Alternative Architect（必要な場合だけ使用） | read-only |
| Codex GPT-5.4 High | Red Team Reviewer | read-only |
| Codex Sol Extra High | Final Auditor | read-only |

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

## 関連文書

- [review-protocol.md](review-protocol.md) — 設計討論・レビューの具体的手順
- [../decisions/0001-multi-agent-workflow-boundary.md](../decisions/0001-multi-agent-workflow-boundary.md) — この方式の意思決定記録（ADR）
- [step1_repository_audit.md](step1_repository_audit.md) — 導入前のリポジトリ現状監査（Step 1）
- [../../CLAUDE.md](../../CLAUDE.md) — Claude Code向けプロジェクトルール
- [../../AGENTS.md](../../AGENTS.md) — Codex向けプロジェクトルール
