# Claude subagents

## Step 5の目的

Step 5は、[`README.md`](README.md) / [`review-protocol.md`](review-protocol.md) / [`../decisions/0001-multi-agent-workflow-boundary.md`](../decisions/0001-multi-agent-workflow-boundary.md) で定義済みの論理ロールのうち、Claude Code側の4ロールを、プロジェクトスコープのClaude Code subagentsとして実際に定義し（Step 5A）、Agentツールによる明示的な直接起動で実機検証すること（Step 5B）である。Codex側の論理ロール（Independent Architect等）は引き続き `.mcp.json` 経由の `codex-reviewer` MCPサーバー（Step 4、[`mcp-connection.md`](mcp-connection.md)）を通じて呼び出す。

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

Claude Code 2.1.220では `/agents` 実行時に "The /agents wizard has been removed" と表示され、一覧ウィザードは使用できない。そのため、確認はウィザードによる一覧表示ではなく、Agentツールによる各project subagentの明示的な直接起動で行う。

1. Terminal版Claude Codeを、この4ファイルを含むリポジトリ/worktreeのルートから起動する
2. Agentツールで `requirements-auditor` / `simplifier` / `claude-architect` / `design-judge` の各project subagentを、それぞれ明示的に指定して直接起動する
3. 各エージェントについて、read-onlyな簡単なタスク（例: 既存ファイルの監査依頼）を与え、実際にRead/Glob/Grepのみで応答し、ファイルを変更しないことを確認する
4. 各エージェントの応答が、本ファイルおよび各frontmatterで定義した出力フォーマット（Status/Confirmed/Inference/Unknown等）に沿っていることを確認する
5. 呼び出し時に返る一時的な実行識別子（Agent ID）は、リポジトリ文書・commit・PR本文へ記録しない

## 検証結果（Step 5B）

Terminal版Claude Codeから、上記手順で4つのproject subagentsをそれぞれAgentツールにより明示的に直接起動し、以下を確認した。

- **requirements-auditor**: 受入条件・検証方法・commit/push/PR可否が不明な仮タスクに対し、不足情報を勝手に補完せず `Status: BLOCKED` を返した。Confirmed / Inference / Unknownを区別し、Clarifying questionsとNormalized task packetを返した。ファイル変更なし。
- **simplifier**: Markdownリンク1件の追加という単純なタスクに対し、DB・キャッシュ・バックグラウンドワーカーといった不要な過剰設計を除去対象として指摘した。Keep / Remove / Replace / Evidence / Risks / Unknown / Verdictを返し、必要な検証項目は維持した。ファイル変更なし。
- **claude-architect**: Codex側や他の設計案を見ない独立設計案を作成した。Proposal ID・根拠・対象ファイル・変更案・リスク・テスト計画・ロールバック計画・Unknown・Out of scopeを返し、統合設計の作成や最終採用判定は行わなかった。ファイル変更なし。
- **design-judge**: 匿名化した案A・案Bを100点基準で採点し（案A 88点、案B 20点）、採用・不採用理由をリポジトリの証拠と結び付けた。統合設計・テスト計画・ロールバック計画・User approval itemsを返し、提供元やモデル名を推測しなかった。ファイル変更なし。

4エージェントとも、実際のproject subagent名で応答し、read-only（Read/Glob/Grepのみ）で動作し、ファイル変更は一切行わなかった。各frontmatterで指定しているmodel aliasは haiku/haiku/sonnet/opus であるが、これはfrontmatter上の指定にすぎず、実行時にこの指定が優先されるか、実際に解決されたfull model IDが何であるかは確認していない。確認できていない実行時解決の詳細を、本文書には推測で記載しない。呼び出し時に返った一時的な実行識別子（Agent ID）は保存していない。

この手動確認で見つかった軽微な3点を、Step 5Bで各エージェント定義へ反映した。

- **simplifier**: ロールバック案として `git checkout` 等の既存作業を破棄しうる操作を提案していたため、破壊的なロールバック操作を提案しない方針（commit前は逆方向の明示的編集、commit後は `git revert`）を明記した
- **claude-architect**: Data/control flowの見出しを省略していたため、該当しない場合も `N/A` と理由を明記した上で全見出しを必ず出力する方針を明記した
- **design-judge**: 統合設計の一部を「承認不要」と記載していたため、`READY_FOR_APPROVAL` は実装許可を意味せず、すべての変更に実装前のユーザー承認が必要であることを明記し、「承認不要」区分を作らない方針を明記した

## 検証状態

**Verified**

上記の手動確認により、4つのproject subagentsが実際に明示的起動で動作し、read-only性・出力フォーマット・ファイル非変更が確認された。

## Step 6のSkillは未実施

multi-agent-design Skill（Step 6）はまだ作成していない。本Step 5（5A・5B）の範囲は `.claude/agents/` 配下の4ファイルと `subagents.md`・`quality-first-token-policy.md`、および `README.md`/ADRのStep 5関連記述のみであり、Skillの追加は含まない。
