# ADR-0001: Multi-agent workflow boundary

## Status

Accepted

## Date

2026-07-29

## Context

`pokemon_card_ai` リポジトリでは、これまで Claude Code が単独でエージェント（`experiments/agents/raging_bolt/`）の設計・実装・監査を行ってきた。単一モデルによる設計・実装は、思い込みによる見落としや、単一視点でのレビューに留まるリスクがある。

Step 1（リポジトリ監査、[`../agent-workflow/step1_repository_audit.md`](../agent-workflow/step1_repository_audit.md)）でリポジトリの導入可否を確認し、Step 2（既存指示整合、`CLAUDE.md`/`AGENTS.md` の Raging Bolt 構成への統一）を完了した。本ADRはStep 3として、Claude CodeとCodexを併用するマルチエージェント開発ワークフローの境界線を決定記録として残す。

## Decision

- Claude Code（Sonnet）を Main Architect 兼 Implementation Owner とする
- Codex Terra を独立設計者（Independent Architect）とする
- Claude Opus を Design Judge / Integrator とする
- Codex をその他、独立設計（Alternative Architect、必要時のみ）、Red Team、最終監査に利用する
- 統合設計は Design Judge / Integrator（Opus）が匿名評価結果を基に作成する
- 統合設計後にユーザー承認を必須とする
- 実装は承認済みの統合設計に基づき、原則 Sonnet（Implementation Owner）だけが行う
- 他のエージェントは read-only
- 設計討論は最大2ラウンド
- 匿名評価を使用する
- merge はユーザーが判断する
- 現在のアプリケーションコードへ影響させない形で段階導入する

## Role boundaries

論理ロールと現在の希望割り当ては [`../agent-workflow/README.md`](../agent-workflow/README.md) を正とする。要点:

- 論理ロール（Orchestrator/Main Architect/Implementation Owner、Requirements Auditor、Simplifier、Independent Architect、Alternative Architect、Red Team Reviewer、Design Judge/Integrator、Final Auditor）はモデル名と分離して定義する
- Sonnet は Main Architect（独立した主設計案の作成）兼 Implementation Owner。統合設計の作成は担当しない
- Codex Terra は Independent Architect として、Sonnet の案を見る前に独立した実務的設計案を作成する
- Opus は Design Judge / Integrator として、匿名評価・採用不採用判定・統合設計の作成・未解決事項とユーザー承認事項の整理を担当する
- 編集権限を持つのは Implementation Owner のみ。他は read-only（詳細手順は [`../agent-workflow/review-protocol.md`](../agent-workflow/review-protocol.md) の「実装権限」を参照）
- 希望割り当ては運用上のラベルであり、MCP/CLIで確認された実モデルIDではない

## Authentication and billing boundary

これは製品仕様の断定ではなく、**このプロジェクトの運用方針**として記載する。

- OpenAI APIキーを利用した従量課金を前提にしない
- Anthropic APIキーを利用した従量課金を前提にしない
- ログイン済みの ChatGPT Plus版 Codex CLI と Claude Code のサブスクリプション枠を利用する
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

## Secret-management boundary

- APIキー・トークン・認証情報をファイルへ保存しない
- `.env` の内容を出力・commitしない
- カード効果全文・画像URLを `data/` やCSVへ保存しない（`CLAUDE.md`/`AGENTS.md` のセキュリティ制約を継承）
- `.mcp.json` を追加する場合（Step 4以降）、秘密情報・APIキー・トークン・個人固有パスを含めない

## Phased rollout

1. Repository audit
2. Existing instruction alignment
3. Common workflow documentation
4. Codex MCP connection
5. Claude subagents
6. Multi-agent design Skill
7. Design-only trial
8. Small implementation trial
9. Reusable template extraction

**Step 4以降はまだ未実施。** 本ADRの時点で存在するのはStep 1〜3の成果物のみであり、`.mcp.json` / `.claude/agents/` / `.claude/skills/` はまだ作成されていない。

## Consequences

- 設計判断に複数の独立した視点が入り、単一モデルの見落としリスクが下がる
- レビュー・匿名評価・最終監査の分だけ、単純なタスクに対しては工数が増える（そのため「適用範囲」で対象を限定している）
- 役割をモデル名でなく論理ロールで定義したことで、将来モデルの入れ替えが発生しても文書を書き直す必要が最小限になる
- 希望割り当てが実モデルIDと未確認のままの間は、Step 3の文書はワークフローの設計図であり、実行可能な設定ではない

## Alternatives considered

- **Sonnet単独で設計から実装まで行う** — 既存の運用方式そのもの。単一視点のリスクを解消しないため今回は採用せず、マルチエージェント化の対象とした
- **全エージェントに編集権限を与える** — 変更の衝突・意図しない上書き・監査対象の分散を招くため採用しない。編集権限をImplementation Ownerに一本化した
- **最初からMCP・subagents・Skillを一括導入する** — 未検証の接続・モデルIDを前提にした設定を先に作ることになり、Step 1で指摘された「未確認事項をハードコードしない」方針に反するため、文書化（Step 3）を先行させ、接続確認（Step 4以降）を分離した
- **OpenAI/Anthropic APIキーを直接利用する** — 従量課金と秘密情報管理の負担が増えるため採用せず、既存のサブスクリプション枠を利用する方針とした
- **アプリリポジトリ内に別のGitリポジトリを作る** — Step 1監査で入れ子Gitが存在しないことを確認済みであり、新たに作る理由もないため採用しない

## Follow-up steps

- Step 4: Codex MCP接続の実モデルID・接続名をローカル環境で確認する
- Step 5: Claude subagentsの定義
- Step 6: multi-agent-design Skillの追加
- Step 7以降: 設計のみの試行 → 小規模実装の試行 → 再利用可能なテンプレート抽出

各Stepはユーザーが明示的に指示した範囲でのみ着手する（[`../../CLAUDE.md`](../../CLAUDE.md) / [`../../AGENTS.md`](../../AGENTS.md) のフェーズ制御ルールを継承）。
