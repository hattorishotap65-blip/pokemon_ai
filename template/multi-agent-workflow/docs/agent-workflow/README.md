# マルチエージェント開発ワークフロー

Claude CodeとCodexを併用してこのプロジェクト（{{PROJECT_NAME}}）を開発するための、共通ワークフロー文書の入口。

このディレクトリの文書は**役割分担・進め方・レビュー手順**だけを扱う。アプリケーション固有の実装詳細・性能改善案・戦略文書は複製しない（それらは {{PROJECT_SPECIFIC_DOCS}} を参照）。

## 目的

- Claude CodeとCodexを、役割を分離して利用する
- 独立した設計案を比較する
- 1つのモデルの思い込みで実装しない
- 実装前に安全性、根拠、テスト可能性を確認する
- ユーザーが明示したフェーズ・ステップだけを実施する

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

通常時は、Main Architectの主設計案と Independent Architectの独立設計案の**最低2案**を比較する。Alternative Architect は重大な対立・追加案が必要な場合・またはユーザーが指定した場合にのみ追加する（使用しない場合も2案比較は実施する）。

## 現在の実行主体の割り当て

以下は、上記の論理ロールを実際にどのモデル・ツールへ割り当てているかを記録する節である。導入先プロジェクトごとに、実際の割り当てを記入すること。full model ID（特定バージョンのモデル識別子）は記載しない。MCPやCLIで実際に確認された接続名・モデルIDを使う場合も、確認前の希望のみをハードコードしない。

| 論理ロール | 割り当てる実行主体（記入） | 権限 |
|---|---|---|
| Orchestrator / Main Architect / Implementation Owner | （記入欄） | 編集可 |
| Requirements Auditor | （記入欄） | read-only |
| Simplifier | （記入欄） | read-only |
| Design Judge / Integrator | （記入欄） | read-only |
| Independent Architect | （記入欄） | read-only |
| Alternative Architect（重大な対立・追加案が必要な場合・またはユーザー指定時のみ使用） | （記入欄） | read-only |
| Red Team Reviewer | （記入欄） | read-only |
| Final Auditor | （記入欄） | read-only |

Main Architect / Implementation Owner の役割を担う実行主体は「統合設計の作成」担当ではない。統合設計は Design Judge / Integrator が匿名評価結果を基に作成し、ユーザーが承認したものを Implementation Owner が実装する。

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
11. Implementation Ownerだけが実装
12. テスト
13. Codex最終監査
14. ユーザーによるマージ判断

具体的な手順・入力フォーマット・証拠区分・停止条件は [`review-protocol.md`](review-protocol.md) を参照。この方式を採用した背景・境界線の決定記録は [`../decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md`](../decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md) を参照。

## 導入状況

導入先プロジェクトでの導入・検証の進み具合を、以下のような表で記録すること（フェーズ名・ステップ名は導入先プロジェクトが定めるものであり、このテンプレート自体の抽出元プロジェクトの番号を引き継がない）。

| フェーズ・ステップ | 状態 |
|---|---|
| （記入欄: 例 — Codex MCP接続） | （記入欄: 未実施 / 進行中 / 完了） |
| （記入欄: 例 — Claude project subagents導入） | （記入欄） |
| （記入欄: 例 — design-only Skill導入） | （記入欄） |
| （記入欄: 例 — design-only trial） | （記入欄） |
| （記入欄: 例 — small implementation trial） | （記入欄） |

各項目の詳細な確認手順・確認結果は、[`mcp-connection.md`](mcp-connection.md) / [`subagents.md`](subagents.md) / [`multi-agent-design-skill.md`](multi-agent-design-skill.md) の「検証結果」節、および [`trial-log-template.md`](trial-log-template.md) を使って記録した個別の試行記録を参照。

## 関連文書

- [mcp-connection.md](mcp-connection.md) — Codex MCP接続設定と接続確認結果
- [subagents.md](subagents.md) — Claude Code project subagentsの定義と実機確認結果
- [multi-agent-design-skill.md](multi-agent-design-skill.md) — read-only design-only Skillの定義と実機確認結果
- [quality-first-token-policy.md](quality-first-token-policy.md) — 判断品質を維持しながら重複コンテキストを削減する共通方針
- [review-protocol.md](review-protocol.md) — 設計討論・レビューの具体的手順
- [git-safety.md](git-safety.md) — Git安全チェックリスト
- [troubleshooting.md](troubleshooting.md) — トラブルシューティング
- [repository-audit-template.md](repository-audit-template.md) — 導入前のリポジトリ現状監査用の空の記入骨組み
- [trial-log-template.md](trial-log-template.md) — 設計専用トライアル・小規模実装トライアルの記録用の空の記入骨組み
- [../decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md](../decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md) — この方式の意思決定記録（ADR）のテンプレート
- 導入先プロジェクトのプロジェクトルール文書（Claude Code向け・Codex向けの、それぞれのプロジェクト固有ルール文書。[`../../PROJECT_RULES_SNIPPET.md`](../../PROJECT_RULES_SNIPPET.md) を参照）
