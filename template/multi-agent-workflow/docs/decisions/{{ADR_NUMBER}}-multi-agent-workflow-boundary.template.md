# ADR-{{ADR_NUMBER}}: Multi-agent workflow boundary

## Status

（記入欄 — 例: Proposed / Accepted）

## Date

（記入欄 — YYYY-MM-DD）

## Context

（記入欄 — {{PROJECT_NAME}} において、このマルチエージェント開発ワークフローを導入する背景・経緯を記入する。既存の開発体制、単一モデルによる設計・実装のリスク認識、導入前に実施した監査等があれば、その内容とリンク先を記入する）

## Decision

- 論理ロール「Orchestrator / Main Architect / Implementation Owner」を担う実行主体を定める
- 論理ロール「Independent Architect」を担う実行主体を定める
- 論理ロール「Design Judge / Integrator」を担う実行主体を定める
- 論理ロール「Alternative Architect」（必要時のみ）・「Red Team Reviewer」・「Final Auditor」を担う実行主体を定める
- 統合設計は Design Judge / Integrator が匿名評価結果を基に作成する
- 統合設計後にユーザー承認を必須とする
- 実装は承認済みの統合設計に基づき、原則 Implementation Owner だけが行う
- 他のロールは read-only
- 設計討論は最大2ラウンド
- 匿名評価を使用する
- mergeはユーザーが判断する
- 現在のアプリケーションコードへ影響させない形で段階導入する

## Role boundaries

論理ロールと実行主体の割り当ては [`../agent-workflow/README.md`](../agent-workflow/README.md) を正とする。要点:

- 論理ロール（Orchestrator/Main Architect/Implementation Owner、Requirements Auditor、Simplifier、Independent Architect、Alternative Architect、Red Team Reviewer、Design Judge/Integrator、Final Auditor）はモデル名と分離して定義する
- Main Architect / Implementation Owner を担う実行主体は、独立した主設計案の作成と、承認済み統合設計の実装を担う。統合設計の作成は担当しない
- Independent Architect を担う実行主体は、Main Architectの案を見る前に独立した実務的設計案を作成する
- Design Judge / Integrator を担う実行主体は、匿名評価・採用不採用判定・統合設計の作成・未解決事項とユーザー承認事項の整理を担当する
- 編集権限を持つのは Implementation Owner のみ。他は read-only（詳細手順は [`../agent-workflow/review-protocol.md`](../agent-workflow/review-protocol.md) の「実装権限」を参照）
- 実行主体の割り当ては運用上のラベルであり、MCP/CLIで確認された実モデルIDとは限らない。確認できていないモデルIDを設定へハードコードしない
- `.claude/agents/` 配下のClaude project subagentsは、いずれもfull model IDを固定せずmodel aliasのみを使用する。全エージェントread-onlyで、`tools` は `Read`/`Glob`/`Grep` のみ。オーケストレーションは親のClaude Codeセッションが行い、subagent同士が直接連鎖する設計にはしていない（詳細は [`../agent-workflow/subagents.md`](../agent-workflow/subagents.md)）
- `.claude/skills/{{DESIGN_SKILL_NAME}}/SKILL.md` として追加するプロジェクトスコープSkillは、ユーザーの明示起動のみで動作する（`disable-model-invocation: true`）。`model` override・`allowed-tools`固定は設定せず、実行時の親Claude Codeセッションの設定に委ねる（詳細は [`../agent-workflow/multi-agent-design-skill.md`](../agent-workflow/multi-agent-design-skill.md)）

## Authentication and billing boundary

これは製品仕様の断定ではなく、**このプロジェクトの運用方針**として記載する。

- OpenAI APIキーを利用した従量課金を前提にしない
- Anthropic APIキーを利用した従量課金を前提にしない
- ログイン済みのCodex CLIとClaude Codeの既存契約枠を利用する
- APIキー、トークン、認証情報はリポジトリへ保存しない
- 課金設定や認証設定はリポジトリ文書から変更しない

## Repository and Git boundary

- 入れ子のGitリポジトリを作らない
- `git add .` を使用しない
- 対象ファイルだけをstageする
- 未コミット変更を破棄しない
- 自動commit、auto-mergeを行わない
- ユーザーの明示指示なしにpush、PR、mergeしない
- 設計作業ではアプリコードを変更しない

詳細は [`../agent-workflow/git-safety.md`](../agent-workflow/git-safety.md) を参照。

## Secret-management boundary

- APIキー・トークン・認証情報をファイルへ保存しない
- `.env` の内容を出力・commitしない
- `.mcp.json` を追加する場合、秘密情報・APIキー・トークン・個人固有パスを含めない

導入先プロジェクト固有の追加のセキュリティ制約（例: 特定のデータをリポジトリへ保存しない等）があれば、{{PROJECT_SPECIFIC_DOCS}} を参照し、ここに追記する。

## Phased rollout

（記入欄 — 導入先プロジェクトが実際にこのワークフローを導入する際の段階・フェーズ・ステップを記入する。このテンプレート自体の抽出元プロジェクトの番号を引き継がない）

このワークフローで生じる変更は、最終的に既定ブランチ `{{DEFAULT_BRANCH}}` への反映を前提とする。mergeのタイミング・要否はユーザーが判断する（[`git-safety.md`](../agent-workflow/git-safety.md) を参照）。

## Consequences

（記入欄 — このワークフローを導入した結果として想定される、または実際に確認された利点・コストを記入する）

## Alternatives considered

- **単一の実行主体だけで設計から実装まで行う** — 単一視点による見落としのリスクを解消しないため、マルチエージェント化の対象とした
- **全ロールに編集権限を与える** — 変更の衝突・意図しない上書き・監査対象の分散を招くため採用しない。編集権限をImplementation Ownerに一本化する
- **接続・subagent・Skillを未検証のまま一括導入する** — 未検証の接続・モデルIDを前提にした設定を先に作ることになるため、まず文書化・境界の明確化を先行させ、接続確認・subagent確認・Skill確認を段階的に分離して実施する
- **OpenAI/Anthropic APIキーを直接利用する** — 従量課金と秘密情報管理の負担が増えるため採用せず、既存の契約枠を利用する方針とする
- **アプリリポジトリ内に別のGitリポジトリを作る** — 入れ子のGitリポジトリを新たに作る理由がないため採用しない

## Follow-up steps

（記入欄 — このADRに基づいて今後実施予定・実施済みの作業を記入する）

各フェーズ・ステップは、ユーザーが明示的に指示した範囲でのみ着手する（プロジェクトルール文書（CLAUDE.md / AGENTS.md 相当）のフェーズ制御ルールを継承）。
