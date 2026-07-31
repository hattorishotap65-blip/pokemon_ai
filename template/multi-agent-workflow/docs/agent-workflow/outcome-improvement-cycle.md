# Outcome Improvement Cycle

Outcome Improvement Cycleは、Pokemon AI、RAG、Webアプリ、batch処理などで「何を試すか」と「外部測定結果を採用できるか」を分離する汎用ワークフローである。アプリ固有の目標、metric、dataset、segment、閾値は[App Profile](app-profile.md)に置き、汎用フローへ埋め込まない。

既存の`multi-agent-design`はdesign-only/read-onlyのまま保持する。本Cycleは、その設計規律を参照しつつ、明示承認後の実装、二段階外部評価、決定論的Gatekeeper、release boundaryを追加する別のopt-inワークフローである。

## 適用範囲

成果に影響する変更へ適用する。例:

- policy、scoring、search、rollout、evaluation function
- parameter、deck、opponent prediction、decision feature
- RAG retrieval/ranking/prompt/evaluator
- Webのユーザー行動やreliabilityへ影響するロジック
- batchのcorrectness、throughput、error handlingへ影響するロジック

docs/comment/formattingだけ、挙動を変えないCI、挙動を変えないrenameなどは、プロジェクト規則が別途要求しない限りフルサイクルを強制しない。

## 汎用層とアプリ固有層

汎用control planeはphase、role、artifact、有限上限、停止条件だけを持つ。application planeはApp Profile、外部evaluator、Evidence Bundle、domain固有metricを持つ。

```text
App Profile
  -> Requirements Audit
  -> Evidence Registry
  -> independent frozen proposals (exactly 2)
  -> Falsification
  -> Blind Design Judge (A->B and B->A)
  -> Primary design + optional fallback
  -> Selected Design Refinement (bounded; default/max v1 = 1)
  -> Alignment Judge
  -> Implementation Owner
  -> Test Audit
  -> Screening Evaluation
  -> Deterministic Gatekeeper
       PASS_TO_CONFIRMATION -> Confirmation Evaluation -> Gatekeeper
       FAIL(primary only)   -> fixed fallback (max 1; primary failure Evidence required)
       INSUFFICIENT         -> missing evidence for same candidate only
       BLOCKED              -> stop
  -> Final Audit
  -> only PASS and authorized: commit/push/Draft PR
  -> merge only after explicit user instruction
```

Design Judgeは何を試すかを選ぶ。Gatekeeperは外部測定値が事前条件を満たしたかだけを判定する。この2つを混同してはならない。

## 論理ロール

| Role | Write権限 | 責務 |
|---|---|---|
| Orchestrator | なし | phase順序、artifact、上限、停止条件の管理 |
| Requirements Auditor | なし | 必須値、scope、permission、Profile readinessの監査 |
| Evidence Auditor | なし | Confirmed/Inference/Unknownを一次資料へ結び付ける |
| Independent Designers | なし | 相互非開示でexactly 2案を作る |
| Falsifier | なし | Blocker/Major/Minor/Test gapへ分類 |
| Blind Design Judge | なし | 固定rubricをA→B/B→Aの両順で評価 |
| Design Refiner | なし | 選定案を実装可能仕様にする |
| Design Challenger | なし | 具体化仕様を反証する |
| Final Refiner | なし | 必要な指摘だけを反映し却下理由を残す |
| Alignment Judge | なし | 選定案との一致をAPPROVE/CHANGES_REQUIRED/REJECTで判定 |
| Implementation Owner | project規則内 | 唯一の実装者 |
| Test Auditor | なし | 必須テストと未確認事項を監査 |
| Gatekeeper | なし | Profile/Evidenceを決定論的比較 |
| Final Auditor | なし | scope、tests、gate、保護対象、release条件を最終監査 |

物理的なagent/threadが利用できない場合、利用できないroleを実行したと偽装しない。same-modelだけでbootstrapした場合はExecution Traceに明記し、heterogeneous review済みと表現しない。

## Artifact契約

handoffは口頭の印象ではなく、次のartifact IDとrevisionで管理する。Agent ID、thread ID、秘密、個人絶対pathは保存しない。

| Artifact | 最低限の内容 |
|---|---|
| Cycle Request | purpose、scope、permission、Profile参照、Cycle ID、固定Primary/Fallback ID |
| Requirements Verdict | READY/BLOCKED、missing values、Unknown |
| Evidence Registry | Evidence ID、Confirmed/Inference/Unknown、一次資料 |
| Frozen Proposal Bundle | proposal ID、固定revision、独立性宣言 |
| Falsification Report | 各指摘のseverityと必要test |
| Design Decision | score、primary/fallback、order sensitivity、rejection reasons |
| Refined Design | exact allowlist、schema、CLI、acceptance、rollback |
| Alignment Verdict | APPROVE/CHANGES_REQUIRED/REJECT |
| Implementation Manifest | baseline/candidate immutable binding、Cycle ID、変更path、tests |
| Evidence Bundle | [App Profile契約](app-profile.md)に従うcandidate role、Evidence round、外部`delta_stats`を含む測定値 |
| Gate Verdict | 5 verdict、reason code、eligible actions |
| Final Audit | scope、tests、gate、保護対象、Unknown、release decision |

後続roleは上流artifactを黙って書き換えない。修正は新revisionとして記録する。

## Requirements Audit

Profileの必須値を最初に検証する。値がない場合、もっともらしいdefaultで補完しない。

- `example_only`は設計・validation fixtureには使えるが、候補採用には使えない。
- `active` Profileに未解決Unknownが残る場合はBLOCKED。
- Profile permissionはユーザー指示やrepo規則より広い権限を作れない。permission依存の相互矛盾、allowed/prohibited pathの同一・祖先・子孫競合はBLOCKED。
- evaluation target、immutable baseline binding、Cycle ID、Primary/Fallback ID、metric、segment、stage criteria、Evidence round上限が確定していなければ実装・評価へ進まない。

## Design tournament

1. 同一のCycle Request、Profile、Evidence Registryを2人のDesignerへ渡す。
2. 両案完成まで相互に見せない。
3. 2案を固定してからFalsificationを行う。
4. 作者・model・vendor・thread情報を落として匿名化する。
5. 固定rubricでA→B、B→Aの両順を評価する。
6. 順序だけでwinnerが変われば`INSUFFICIENT_EVIDENCE`として止める。
7. Primary designとfallback design最大1件を事前選定する。

サイクル中の新規案追加、投票数だけの採用、LLM Judgeの文章によるGate上書きを禁止する。

固定rubricは、portability、generic/application separation、Profile expressiveness、Gate clarity、safety、simplicity、testability、template alignment、rollback、extensibilityを含む。

## Selected Design Refinement

既定は1回、v1上限も1回である。

1. Design Refinerがexact allowlist、data contract、状態遷移、test、rollbackへ具体化する。
2. Design Challengerがread-onlyで反証する。
3. Final Refinerが採用指摘と却下理由を記録する。
4. Alignment Judgeが元のDesign Decisionと要件への整合を判定する。

`APPROVE`だけがImplementationを解放する。重大な新証拠が見つかり第2回が必要になった場合、上限を勝手に増やさずBLOCKEDとしてユーザーへ報告する。

## ImplementationとTest Audit

Implementation Ownerだけが変更する。Reviewer、Judge、Auditorはread-onlyである。ownerは実装前baseline、exact target files、protected pathsを固定し、無関係なdirty変更を触らない。

Test Auditは少なくとも次を確認する。

- Profile正常／異常系と5 direction
- primary/guardrail/segment/stage coverage
- screening/confirmationと5 verdict
- dataset/protocol/profile/Cycle/baseline/candidate immutable binding、candidate role、Evidence round
- 外部Evaluator生成`delta_stats`を使用し、Gatekeeperがdelta CIを合成しないこと
- fallback/refinement/evidence追加上限
- permission矛盾
- shell-like文字列が実行されないこと
- Gatekeeperがwrite/network/Git/subprocessを持たないこと
- template manifest、source-integrity、strict bytes、既存ファイル非上書き
- current repoのprotected paths、PR除外、original dirty repo不変

実行していないtestは成功として報告しない。

## Evaluation tournament

Primary candidateを先に実装し、Test Audit承認後にscreeningする。screeningが`PASS_TO_CONFIRMATION`のときだけconfirmationへ進む。

- primary screeningのprimary criterionだけが`FAIL`: 固定済みfallbackを、primary failure Evidenceを添えて最大1件評価可
- guardrail/catastrophic `FAIL`: fallbackなし
- `INSUFFICIENT_EVIDENCE`: 同じcandidate artifactの不足測定だけを固定round上限内で追加
- `BLOCKED`: 即停止
- primary/fallback双方`FAIL`: baselineを維持して終了

candidate間でCycle ID、baseline、candidate role/ID、artifact binding、dataset、protocolを黙って変更しない。変更が必要なら新Cycleとする。

## Deterministic Gatekeeper

[`tools/outcome_gatekeeper.py`](../../tools/outcome_gatekeeper.py)はPython標準ライブラリだけのread-only CLIである。外部evaluatorが生成したEvidenceとProfileを比較し、`PASS`、`PASS_TO_CONFIRMATION`、`FAIL`、`INSUFFICIENT_EVIDENCE`、`BLOCKED`のいずれかを返す。

Gatekeeperは評価の実行、統計の推定、candidate/baseline CIからのdelta CI合成、候補選択、fallback実装、Git操作、commit、push、PR、mergeを行わない。`basis=delta`では外部Evaluatorの`delta_stats`だけを使用し、同じ入力bytesと環境非依存の規則から同じJSON結果を返す。

## Release boundary

commit/push/Draft PRは、次の全条件を満たした場合だけ行う。

- Alignment Judge APPROVE
- Test Auditor APPROVE
- 必須test成功
- confirmation Gatekeeper PASS
- Final Auditor APPROVE
- protected/out-of-scope差分なし
- original dirty repo不変
- user/repo/Profile permissionsの共通部分が許可され、依存矛盾とpath競合がない

Profileの`PASS`は操作を自動実行しない。mergeは常にユーザーの明示指示が必要である。Profileがheterogeneous reviewを要求する場合、その完了前にDraft解除またはmergeを行わない。

## Rollback

- commit前: exact allowlist内の今回変更だけを明示的な逆編集で戻す。
- commit後: 対象commitの`git revert`を提案し、承認後に実施する。
- `reset`、`stash`、`clean`、変更破棄目的の`checkout`をrollback手段にしない。
- partial adoptionが失敗した場合、新しいopt-in Skill/Profile/Gatekeeperを外して既存design-only workflowを維持する。

## PortabilityとKnown Unknown

ProfileとGatekeeperはstdlib、strict JSON、repo相対pathでOS依存を抑える。template verifierの既存portable checksを維持する。ただし、特定OSまたはproduction repositoryで実行していない場合は`Unknown`として報告し、検証済みと表現しない。
