# App Profile v1

App Profileは、アプリ固有の改善目標と外部評価条件を、汎用Outcome Improvement Cycleへ渡すversioned JSON契約である。Profileは評価を実行する設定ではない。Profile内の文字列をcommand、module、URL、scriptとして実行してはならない。

## 安全境界

- JSONとPython標準ライブラリだけを使用する。
- GatekeeperはProfileと外部Evidenceを読み、比較結果をstdoutへ返すだけである。
- shell、subprocess、network、Git、ファイル書込み、測定実行、候補実装を行わない。
- Profileのpermissionは既存のユーザー指示とリポジトリ規則を狭める上限であり、権限を新たに付与しない。
- 必須値は推測で補わない。`active` Profileの未解決事項はRequirements AuditでBLOCKEDにする。
- 配布サンプルは`example_only`である。validateとdigestは可能だが、evaluateは必ず`BLOCKED`になる。

## JSONとcanonical digest

全objectは定義済みkeyだけを許可し、unknown keyとduplicate keyを拒否する。UTF-8 BOM、NaN、Infinity、boolの数値利用を拒否する。評価用の数値は有限のcanonical Decimal文字列とする。指数表記、不要な先頭0、末尾0、`-0`は使わない。

Profile digestは、検証済みobjectを次の規則でcanonical化したbytesのSHA-256 lowercase hexである。

```python
json.dumps(
    profile,
    sort_keys=True,
    ensure_ascii=False,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
```

末尾newlineとBOMは付けない。array順を保持し、Unicode normalizationは行わない。Profile自身にはdigest fieldを置かず、Evidence側が`profile_sha256`で参照する。

## Profile必須フィールド

Top-levelは次のkeyをすべて必須とし、それ以外を拒否する。

| Key | 内容 |
|---|---|
| `schema_version` | v1は`1.0` |
| `profile_id` / `profile_version` | 安定IDとversion |
| `status` | `active`または`example_only` |
| `applicability` | 適用する変更種別、説明、除外 |
| `objective` | 目的とprimary metric ID |
| `baseline` | baseline artifact IDとimmutable ref |
| `evaluation_targets` | stageが参照するdataset/protocol identity |
| `segments` | 明示的な評価segment |
| `metrics` | primary 1件とguardrail 1件以上 |
| `stages` | screeningとconfirmationの証拠量・CI・criteria |
| `tournament` | 有限の案数、fallback、refinement、時間上限 |
| `change_scope` | 変更可能／禁止のrepo相対path |
| `permissions` | implementation/commit/push/PR/merge上限 |
| `reporting` | 必須報告項目とEvidence Registry要否 |
| `rejected_hypothesis_memory` | 再試行を避ける棄却仮説。空配列可 |
| `unresolved_unknowns` | 未解決項目。空配列可 |

IDは`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`、SHA-256はlowercase 64 hexとする。各namespace内でIDは一意、referenceはcase-sensitive exact matchとする。

### Applicabilityとscope

`applicability`は`description`、非空の`change_kinds`、非空の`exclusions`を持つ。`change_scope`は非空の`allowed_paths`と`prohibited_paths`を持つ。pathはPOSIX形式のrepo相対pathだけを許可し、absolute、UNC、drive-relative、backslash、`.`、`..`、制御文字を拒否する。

### Metrics

各metricは次を持つ。

- `id`
- `role`: `primary`または`guardrail`
- `direction`: `maximize` / `minimize` / `target` / `threshold` / `range`
- `unit`
- `required_segments`: 1件以上のsegment ID

Profile全体でprimaryは厳密に1件、guardrailは1件以上とする。error、timeout、illegal action、decision timeなどの品質条件も、アプリ固有keyではなく通常のguardrail metricとして表す。

### Evaluation targetsとstages

各evaluation targetは`id`、`dataset_id`、`dataset_version`、`dataset_sha256`、`protocol_id`を持つ。screeningとconfirmationは、異なるtargetを参照できる。

各stageは次を持つ。

- `evaluation_target_id`
- `min_total_observations`
- `min_observations_per_segment`
- `uncertainty`: `required=true`、method ID、confidence level
- `criteria`
- `catastrophic_criteria`

`criteria`は各`metric × required_segment`について厳密に1件必要である。wildcard、暗黙のsegment補完、aggregateによるsegment代替は認めない。catastrophic criteriaは任意件数だが、同じmetric/segmentの重複を認めない。

Criterionは`metric_id`、`segment_id`、`basis`、`statistic`、`parameters`を持つ。

- `basis`: `candidate`または`delta`
- maximize: `statistic=lower`、`parameters.limit`
- minimize: `statistic=upper`、`parameters.limit`
- target: `statistic=interval`、`parameters.target/tolerance`
- threshold: `statistic=estimate|lower|upper`、`parameters.operator=gte|lte`と`limit`
- range: `statistic=interval`、`parameters.lower/upper`

`delta`のintervalは、外部Evidenceのcandidate/baseline intervalから保守的に算出する。

- estimate = candidate estimate - baseline estimate
- lower = candidate lower - baseline upper
- upper = candidate upper - baseline lower

Gatekeeperは平均、再標本化、CI計算、最新値選択を行わない。

### Tournament上限

v1は次を必須とする。

- `independent_proposals = 2`
- `primary_candidates = 1`
- `fallback_candidates = 0..1`
- `refinement_rounds = 0..1`
- `additional_evidence_rounds = 0..3`
- `max_design_minutes = 1..1440`
- `max_evaluation_minutes = 1..10080`

unlimited、負数、上限超過を拒否する。今回の標準フローはrefinement 1回である。

### Permissions

`permissions`は次の5 keyだけを持つ。

| Key | 許可値 |
|---|---|
| `implementation` | `denied` / `after_alignment_approve` |
| `commit` | `denied` / `after_confirmation_pass` |
| `push` | `denied` / `after_confirmation_pass` |
| `pull_request` | `denied` / `after_confirmation_pass` |
| `merge` | `denied` / `explicit_user_approval_after_heterogeneous_review` |

Gatekeeperはeligibleかどうかを報告するだけで操作しない。`example_only`では全操作が非eligibleである。mergeは数値条件だけではeligibleにならない。

## Evidence Bundle

EvidenceはProfileとは別のstrict JSONで、外部evaluatorが作る。必須top-level keyは次のとおり。

- `schema_version`
- `evidence_id`
- `stage`: `screening`または`confirmation`
- `profile_id` / `profile_version` / `profile_sha256`
- `candidate_identity` / `baseline_identity`
- `evaluation_target_id`
- `dataset_identity`: `id` / `version` / `sha256`
- `protocol_identity`
- `uncertainty`: stageと一致する`method` / `confidence_level`
- `total_observations`
- `cells`

candidateとbaselineは異なるIDでなければならない。Profile、stage、target、dataset、protocolのidentity不一致は`BLOCKED`である。

各cellの一意keyは`(metric_id, segment_id)`であり、次を持つ。

- `observations`
- `baseline_stats`: `estimate` / `lower` / `upper`
- `candidate_stats`: `estimate` / `lower` / `upper`

statsはcanonical Decimal文字列で、`lower <= estimate <= upper`を満たす。required cell欠落または観測数不足は`INSUFFICIENT_EVIDENCE`、duplicate/extra/unknown cellは`BLOCKED`である。

## Verdictと遷移

優先順位は次のとおり。

1. `BLOCKED`: schema、identity、digest、permission契約などが不正
2. `INSUFFICIENT_EVIDENCE`: 構造は妥当だがrequired evidence量が不足
3. `FAIL`: catastrophic、guardrail、primary criterionのいずれかが未達
4. screening全合格: `PASS_TO_CONFIRMATION`
5. confirmation全合格: `PASS`

Primary screeningのprimary criterionだけが`FAIL`した場合に限り、事前選定済みfallbackを最大1件評価できる。guardrail/catastrophic FAIL、BLOCKED、INSUFFICIENTではfallbackへ進まない。INSUFFICIENTでは同一候補の不足Evidenceだけを、Profileの有限上限内で追加する。

## CLI

```text
python tools/outcome_gatekeeper.py validate-profile PROFILE
python tools/outcome_gatekeeper.py digest-profile PROFILE
python tools/outcome_gatekeeper.py evaluate --profile PROFILE --evidence SCREENING_EVIDENCE
python tools/outcome_gatekeeper.py evaluate --profile PROFILE --evidence SCREENING_EVIDENCE --confirmation-evidence CONFIRMATION_EVIDENCE
```

出力はstdout上の単一sorted JSONだけである。秘密、raw payload、absolute pathをstderrへ出さない。locale、time、environmentへ判定を依存させない。ファイル出力optionは持たない。

| 結果 | Exit code |
|---|---:|
| validate/digest success、PASS | 0 |
| PASS_TO_CONFIRMATION | 10 |
| FAIL | 20 |
| INSUFFICIENT_EVIDENCE | 30 |
| BLOCKED、validate/digest failure | 40 |

## サンプルの扱い

`pokemon-ai.example.json`と`rag-quality.example.json`は表現力と検証のfixtureであり、本番の合格基準ではない。両方とも`status=example_only`とし、説明用の値を実運用defaultへ昇格させない。実運用ProfileはRequirements Auditで目的、baseline、dataset、各threshold、Evidence量、permissionを確定した後に別versionとして作る。
