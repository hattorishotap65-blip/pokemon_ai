# multi-agent-design Skill

## Step 6の目的

Step 6は、Step 1〜5で整備した論理ロール（[`README.md`](README.md)）、Claude project subagents（Step 5、[`subagents.md`](subagents.md)）、Codex MCP接続（Step 4、[`mcp-connection.md`](mcp-connection.md)）を、親Claude Codeセッションが1つのSkillとして順番にオーケストレーションできるようにすることである。Step 6Aの範囲はSkillの作成と静的検証まで、Step 6Bの範囲は手動実機確認の結果反映とcommit/push/PR作成までであり、Step 7（設計のみの試行）は含まない。

## Skillの場所とSkill名

- Skill名: `multi-agent-design`
- 配置: [`../../.claude/skills/multi-agent-design/SKILL.md`](../../.claude/skills/multi-agent-design/SKILL.md)（プロジェクトスコープ）

## 実行方法

- `/multi-agent-design [設計タスク]` の形で、ユーザーが明示的に起動する
- `disable-model-invocation: true` により、モデルが自動判断で起動することはない。アーキテクチャ変更・複数ファイル設計・高リスク変更・性能改善・リファクタリング・テスト戦略設計であっても、ユーザーが明示的に呼ばない限りこのSkillは動かない
- `$ARGUMENTS` が空の場合、いずれのフェーズも開始せず、設計タスクの入力をユーザーへ求めて停止する

## frontmatterに含めていないもの

`model` / `allowed-tools` / `context` / `agent` / `effort` / `hooks` はfrontmatterに含めていない。モデル固定・ツール制限の追加固定・reasoning effortの固定は行わず、実行時の親セッションの設定に委ねる。

## 親セッションがオーケストレーションすること

このSkill自身はコードを実行するプログラムではなく、親のClaude Codeセッションが読み、その指示に従って各フェーズを順番に実行する手順書である。Claude project subagents（`.claude/agents/`）とCodex MCP（`codex-reviewer`）はいずれも親セッションから直接呼び出し、subagent同士やCodexから別ロールを連鎖起動する構成にはしていない（[`subagents.md`](subagents.md)の「subagent同士が直接連鎖しないこと」を継承）。

## 設計専用・read-onlyであること

このSkillは実行全体を通じて設計専用・read-onlyである。ファイルの作成・編集・削除、コード実装、テスト実装、commit・push・PR作成・merge・deploy・外部サービスへの書き込みは、フェーズのいずれにおいても行わない。ユーザーの最初の入力が実装を要求していても、Phase 7のユーザー承認ゲートで必ず停止する。`READY_FOR_APPROVAL` は統合設計を提示できる状態を意味し、実装許可を意味しない。

## 8フェーズ（Phase 0〜Phase 7）

| フェーズ | 内容 |
|---|---|
| Phase 0 | Preflight and safety gate — cwd、対象リポジトリ、設計専用・read-only・ファイル変更禁止・commit/push/PR禁止の確認、codex-reviewer MCPとproject subagentsの利用可否確認。利用不可ならBLOCKEDとして停止し、実行したふりをしない |
| Phase 1 | Requirements audit and normalized task packet — requirements-auditorを明示的に起動。BLOCKEDなら後続agent・Codex MCPを呼ばず停止。READYならNormalized task packet・Task ID・Evidence Registryを作成 |
| Phase 2 | Independent architecture proposals — claude-architect（案1）とcodex-reviewerのcodexツール（案2、Independent Architect、新規スレッド）が、互いの案を見る前に独立して案を完成させる |
| Phase 3 | Simplification and red-team review — simplifier subagentとcodex-reviewerのcodexツール（Red Team Reviewer、新規read-onlyスレッド）による、匿名化した2案へのレビュー。一次証拠を再確認できなかった場合はEvidence limitationとして記録する |
| Phase 4 | Evidence-based rebuttal rounds — 最大2ラウンド。Codex側は初期スレッドをcodex-replyで継続、Claude側は親セッションが元Proposal IDとEvidence Registryに基づき応答を構成 |
| Phase 5 | Anonymization — Design Judgeへ渡す前に、Claude/Codex/Anthropic/OpenAI/モデル名・MCPツール名・subagent名・threadId・Agent IDを除去し、案A/案B/(必要時)案Cとして再構成 |
| Phase 6 | Anonymous judging and integrated design — design-judgeを起動し、100点基準（正確性30・根拠の強さ20・安全性/変更範囲遵守20・単純さ/保守性15・テスト可能性/ロールバック性15）で評価し統合設計を作成。判断に重要な事実はRead/Glob/Grepで再確認し、重大なEvidence limitationがあればBLOCKED |
| Phase 7 | User approval gate — BLOCKEDならBlocker等を提示して停止。READY_FOR_APPROVALなら統合設計一式とExecution Traceを提示し、実装へ進んでよいかをユーザーへ明示的に確認して停止。承認前には実装しない |

## requirements-auditorの停止ゲート

Phase 1でrequirements-auditorがBLOCKEDを返した場合、後続のsubagent呼び出し・Codex MCP呼び出しは一切行わない。Blockers・Clarifying questionsを提示して停止する。親セッションが不足情報を勝手に補完することはない。

## 2案の独立性

Phase 2では、claude-architect（Main Architect）とCodex側のIndependent Architectが、同一のNormalized task packetから、互いの初期案を見る前に独立して案を完成させる。両者の初期案が完成するまで、一方をもう一方へ渡さない。

## Codex threadの再利用方針

Phase 2で開いたIndependent Architectの`threadId`は、Phase 4のRound 1/2における同一議論の継続にのみ`codex-reply`で再利用する。Red Team Reviewer（Phase 3）とAlternative Architect（起動時）は、それぞれ別の新規read-onlyスレッドを使用する。`threadId`はいずれもファイル・commit・PR本文へ保存しない。

## Simplifier

Phase 3で、simplifier subagentへ2案を案A/案Bとして匿名で渡し、過剰設計・不要な変更範囲・重複実装・不要な依存・過剰な抽象化を指摘させる。正確性・安全性・必要な証拠・テスト可能性・ロールバック性・必要な性能設計・重大リスク・Unknownは削らせない。

## Red Team Reviewer

Phase 3で、codex-reviewerのcodexツールを新規read-onlyスレッドで使用し、破壊的変更・セキュリティ・データ損失・互換性・性能劣化・失敗モード・テスト不足・ロールバック不能・証拠不足・スコープ逸脱・誤った前提・運用上の問題を確認させる。

## Evidence limitation（Step 6Bで追加）

reviewerまたはarchitectがリポジトリの一次証拠（ファイル）を再確認できなかった場合（ツール・sandboxの問題等）、その事実と影響範囲をEvidence limitationとしてそのロールの出力へ明記する。その結果は通常の完全確認済み証拠としては扱わない。design-judge（Phase 6）は、判断に重要な事実をRead/Glob/Grepで自ら再確認し、それができず正確性・安全性・採否判断へ重大な影響がある場合はBLOCKEDとする。Evidence limitationを隠したり、成功したかのように表現することはしない。

## Alternative Architectの起動条件

通常は呼ばない。次のいずれかに該当する場合のみ、codex-reviewerのcodexツールを新規read-onlyスレッドで起動する（`approval-policy: never`、model overrideなし、reasoning effort固定なし、作者・モデル名を伝えない）。

- 初期2案の両方に重大な欠陥がある
- 重大な対立が解消しない
- 第3の根本的に異なる設計が必要
- Red Teamが両案をREJECT相当と評価した
- ユーザーが第3案を明示的に要求した

呼ばなかった場合も、その理由をExecution Traceへ記録する。

## 最大2回のrebuttal

Phase 4の反論ラウンドは最大2回。Round 1はSimplifierまたはRed Teamから実質的な指摘があった場合に実施する。Round 2は、新しい証拠がある・重大な反証が未解決・安全性/正確性の重大対立が残る・Design Judgeへ渡すには証拠不足、のいずれかに該当する場合のみ実施し、同じ主張の繰り返しでは実施しない。

## 匿名化

Phase 5でDesign Judgeへ渡す前に、Claude/Codex/Anthropic/OpenAI/Sonnet/Opus/Haiku等のモデル・ベンダー名、MCPツール名、subagent名、threadId、Agent ID、作者を推測できる情報をすべて除去し、案A/案B/(必要時)案Cとして再構成する。Proposal ID・Evidence ID・設計内容・利点・欠点・リスク・テスト計画・ロールバック計画・Unknown・Simplifier指摘・Red Team指摘・rebuttal deltaはすべて残す。

## Design Judge

Phase 6で design-judge subagentを起動し、100点基準の評価表・Blockers・Accepted/Rejected elements・Integrated design（対象ファイル・変更順序・テスト計画・ロールバック計画・リスク・Unknown・ユーザー承認事項）・Verdict（READY_FOR_APPROVAL/BLOCKED）を出力させる。多数決ではなく証拠と評価基準に基づく判断とする。

## ユーザー承認ゲート

Phase 7で、READY_FOR_APPROVALの場合は統合設計一式とExecution Traceを提示した上で、実装へ進んでよいかをユーザーへ明示的に確認して停止する。ユーザーの最初の依頼が実装を求めるものであっても、この承認ゲートを経ずに実装することは一切ない。

## 品質優先トークンポリシー

このSkillは [`quality-first-token-policy.md`](quality-first-token-policy.md) をそのまま継承する。目的は短さではなく、重複を除きながら判断品質を維持することである。hard token capは設定せず、reasoning effortを下げて節約することもしない。曖昧さが生じる場合は常に完全なコンテキストを優先する。成功ログは要約可能だが、失敗ログは原因究明に必要な部分を保持する。Proposal ID・Evidence ID・差分による参照を用い、Codexとの同一議論はthreadIdと`codex-reply`で継続し、threadId自体もAgent IDも文書・Gitへ保存しない。Alternative Architectは起動条件を満たす場合のみ呼び、品質を下げる目的でロールを統合することはしない。

## Execution Trace

Skillの最終出力には、実際に起きたことだけを記載するExecution Traceを含める。実行していないロールを`invoked`と記載せず、Agent IDやthreadIdの値そのものは記載しない。

```
- requirements-auditor: invoked / READY
- claude-architect: invoked / proposal received
- Independent Architect (codex): invoked / proposal received
- simplifier: invoked
- Red Team Reviewer (codex): invoked
- codex-reply: same thread reused / yes
- rebuttal rounds: 1
- Alternative Architect: not invoked / trigger absent
- design-judge: invoked / READY_FOR_APPROVAL
- repository files changed: no
- implementation performed: no
```

## 手動確認手順

1. Terminal版Claude Codeを、`.claude/skills/multi-agent-design/SKILL.md` を含むリポジトリ/worktreeのルートから起動する
2. `codex-reviewer` MCPサーバーが `/mcp` 等でconnected状態であることを確認する
3. `requirements-auditor` / `simplifier` / `claude-architect` / `design-judge` の4 project subagentsが利用可能であることを確認する
4. `/multi-agent-design [設計タスク]` を明示的に起動する
5. Phase 0〜7が順番に実行され、各フェーズで規定した停止条件・境界（ファイル変更禁止、requirements-auditorのBLOCKEDゲート、Phase 7のユーザー承認ゲート等）が実際に守られることを確認する
6. Execution TraceにAgent ID・threadIdの値が含まれていないことを確認する
7. 実行を通じてリポジトリのファイルが一切変更されていないことを確認する

## 検証結果（Step 6B）

Terminal版Claude Codeから `/multi-agent-design` を明示的に実行し、上記の手動確認手順に沿って以下を確認した。設計タスクは「マルチエージェントワークフロー設定を検査するread-only CLIツールの設計」とした。この設計は**Step 6の検証用タスク例であり、実装または採用されたものではない**。

- Phase 0: cwd・対象リポジトリ・codex-reviewer MCPの利用可否・4 project subagentsの存在を確認し、Skill実行前のgit statusを取得した
- Phase 1: requirements-auditorを明示的に起動し `Status: READY` を確認した。non-blockingなClarifying questionはUnknownとして後続フェーズへ引き継ぎ、不足事項を勝手に補完しなかった。Task IDを作成した
- Phase 2: claude-architectとCodex Independent Architect（codex-reviewerのcodexツール）が、互いの初期案を見ない状態でそれぞれ独立に案を完成させてから次フェーズへ進んだ
- Phase 3: simplifierを実行した。Codex Red Team Reviewerを新規read-onlyスレッドで実行したが、sandbox helperの問題によりこの実行ではリポジトリファイルを再読込できず、提案の内部整合性を中心にした評価となった。この制限はEvidence limitationとして記録した
- Phase 4: Codex側rebuttalはIndependent Architectの既存threadを `codex-reply` で継続し、新しいスレッドは作成しなかった。Claude側は親Orchestratorが元ProposalとEvidence Registryに基づき応答を構成した。rebuttalは1ラウンドのみ実施し、Round 2は起動条件（新しい証拠・未解決の重大反証等）が成立しなかったため未実施だった
- Alternative Architect: 初期2案に致命的欠陥がなく、重大な未解決対立もなく、Red Teamが両案をREJECT相当と評価しておらず、ユーザーも第3案を要求しなかったため、起動条件不成立として未実施とし、理由をExecution Traceへ記録した
- Phase 5/6: 案A・案Bとして匿名化した上でdesign-judgeを起動し、匿名採点（案A 85 / 案B 79）、Evidence sufficiency、採用要素、却下要素、統合設計、Target files、Test plan、Rollback plan、Risks、Unknown、User approval itemsを出力させ、Verdict `READY_FOR_APPROVAL` を得た。Phase 3のEvidence limitationを踏まえ、design-judgeが判断に重要なリポジトリ事実をRead/Glob/Grepで自ら再確認して補完した
- Phase 7: `READY_FOR_APPROVAL` を実装許可として扱わず、ユーザーへ実装承認を明示的に求めて停止した。ユーザーは実装を承認しておらず、実装は開始していない
- 全体を通じて、Skill実行前後のgit statusが一致し、ファイルの作成・編集・削除は一切なく、commit・push・PRも行っていない。Agent IDとthreadIdはいずれも保存していない

この手動確認で見つかったEvidence limitation（Red Teamがリポジトリ一次証拠を再確認できない場合の扱い）と、8フェーズへの表現統一を、Step 6Bで `SKILL.md` へ反映した。

## 検証状態

**Verified**

上記の手動実機確認により、`/multi-agent-design` の8フェーズが実際に規定通り遷移し、requirements-auditorの停止ゲート・2案の独立性・Codex thread再利用・最大2ラウンドのrebuttal・Alternative Architectの条件付き起動・匿名化・Design Judgeの匿名採点と統合設計・ユーザー承認前の停止・ファイル非変更・Agent ID/threadId非保存が確認された。

## Step 7の履歴上の位置づけ

本Step 6（6A・6B）の完了時点では、Step 7（設計のみの試行）はまだ実施していなかった。その後Step 7は完了しており、結果は [`design-only-trial.md`](design-only-trial.md) に記録されている。この履歴注記は、既存 `.claude/skills/multi-agent-design/SKILL.md` が現在もdesign-only/read-onlyであるという規範を変更しない。
