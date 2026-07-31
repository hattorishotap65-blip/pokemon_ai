# Claude subagents

## 目的

[`README.md`](README.md) / [`review-protocol.md`](review-protocol.md) / [`../decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md`](../decisions/{{ADR_NUMBER}}-multi-agent-workflow-boundary.template.md) で定義済みの論理ロールのうち、Claude Code側の4ロールを、プロジェクトスコープのClaude Code subagentsとして実際に定義し、Agentツールによる明示的な直接起動で実機検証すること。Codex側の論理ロール（Independent Architect等）は引き続き `.mcp.json` 経由のMCPサーバー（[`mcp-connection.md`](mcp-connection.md)）を通じて呼び出す。

## プロジェクトスコープ: .claude/agents/

4エージェントは `.claude/agents/` 配下にMarkdown＋YAML frontmatter形式で定義する。プロジェクトスコープであり、他のリポジトリには影響しない。

## 4エージェントの一覧

| ファイル | 論理ロール | model alias |
|---|---|---|
| [`requirements-auditor.md`](../../.claude/agents/requirements-auditor.md) | Requirements Auditor | haiku |
| [`simplifier.md`](../../.claude/agents/simplifier.md) | Simplifier | haiku |
| [`claude-architect.md`](../../.claude/agents/claude-architect.md) | Primary / Main Architect（独立設計提案） | sonnet |
| [`design-judge.md`](../../.claude/agents/design-judge.md) | Design Judge / Integrator | opus |

full model IDはどのファイルにもハードコードしていない。使用しているのはmodel aliasのみである。

## 各エージェントの役割

- **requirements-auditor**: 設計・実装前に、タスク入力（目的・背景・対象範囲・対象外・変更可能/禁止ファイル・制約・受入条件・検証方法・実装可否・commit/push/PR可否）の過不足を監査する。不足情報を勝手に補完せず、重大な不足はBLOCKEDとする。
- **simplifier**: 既存の設計案に対して、過剰な複雑さ・不要な変更範囲・重複実装・不要な依存・過剰な抽象化を指摘する。正確性・安全性・証拠・テスト可能性・ロールバック性・性能を犠牲にした簡略化は行わない。
- **claude-architect**: Primary/Main Architectとして、Codex側の設計案を見る前に独立した主設計案を作成する。統合設計は作らず、最終採用判定も行わない。
- **design-judge**: Design Judge/Integratorとして、匿名化された案A/案B/(必要時)案Cを評価し、採用・不採用理由を記録した上で統合設計を作成する。匿名評価と統合設計作成の両方を担う唯一のロール。

## 全エージェントread-onlyであること

4エージェントすべて `tools: Read, Glob, Grep` のみを許可しており、Edit / Write / NotebookEdit / Bash / PowerShell / Agent ツールは付与していない。コードの変更・ファイルの作成/編集/削除・commit/push/PR/mergeは一切行えない。

## 親セッションがオーケストレーションすること

4エージェントのいずれも、他のsubagentを起動する前提では設計していない（`tools` にAgentを含めていない）。どのエージェントをどの順序で呼ぶか、結果をどう統合し次のロールへ渡すかは、親のClaude Codeセッション（Orchestrator）が行う。

## subagent同士が直接連鎖しないこと

上記の通り、4エージェントはAgentツールを持たないため、subagentから別のsubagentを直接起動することはできない。連鎖が必要な場合も、必ず親セッションを経由する。

## 品質優先トークンポリシー

4エージェントはすべて [`quality-first-token-policy.md`](quality-first-token-policy.md) に従う。目的は「短さ」ではなく、重複を除きながら判断品質を維持することである。厳しいトークン上限は設けておらず、証拠・重大リスク・Unknown・テスト計画・ロールバック方法・設計案比較の省略は禁止している。

## 手動確認手順

ご使用のClaude Codeのバージョンによっては、`/agents` 実行時に一覧ウィザードが使用できない場合がある。その場合、確認はウィザードによる一覧表示ではなく、Agentツールによる各project subagentの明示的な直接起動で行う。

1. Terminal版Claude Codeを、この4ファイルを含むリポジトリ/worktreeのルートから起動する
2. Agentツールで `requirements-auditor` / `simplifier` / `claude-architect` / `design-judge` の各project subagentを、それぞれ明示的に指定して直接起動する
3. 各エージェントについて、read-onlyな簡単なタスク（例: 既存ファイルの監査依頼）を与え、実際にRead/Glob/Grepのみで応答し、ファイルを変更しないことを確認する
4. 各エージェントの応答が、本ファイルおよび各frontmatterで定義した出力フォーマット（Status/Confirmed/Inference/Unknown等）に沿っていることを確認する
5. 呼び出し時に返る一時的な実行識別子（Agent ID）は、リポジトリ文書・commit・PR本文へ記録しない

## 検証結果

導入先プロジェクトでの実機確認結果は、この節へ記入すること。

- **requirements-auditor**:（記入欄 — Status、返却されたConfirmed/Inference/Unknown、ファイル変更の有無）
- **simplifier**:（記入欄）
- **claude-architect**:（記入欄）
- **design-judge**:（記入欄）

手動確認で見つかった問題点があれば、この節に記録し、必要に応じて各エージェント定義（frontmatter・本文）を修正すること。

## 検証状態

（記入欄 — `Verified` / `Not yet verified` / `Partially verified` のいずれかと、その根拠を記入する。実行していない確認を `Verified` と記載しない）

## design-only Skillは対象外

design-only Skill（例: `{{DESIGN_SKILL_NAME}}`）の追加は、本文書の対象外である。[`multi-agent-design-skill.md`](multi-agent-design-skill.md) を参照。
