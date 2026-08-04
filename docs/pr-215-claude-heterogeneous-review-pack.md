# PR #215 Claude Heterogeneous Review Pack

## How to use this pack

This document is a navigation aid, not review evidence. It was prepared in the same Codex-led workstream that authored the pull request. Do not treat its descriptions, local test reports, prior Codex audit verdicts, or tables as independently verified facts.

Claude must inspect the actual PR diff, source files, tests, and GitHub Actions results before reaching a conclusion. If this pack conflicts with the diff, the diff and repository rules are authoritative. Review must remain read-only: do not edit files, change PR state, merge, push, resolve threads, or post an approval unless separately authorized.

## PR purpose and scope

PR #215 introduces a reusable, application-neutral Outcome Improvement Cycle for Pokemon AI, RAG, Web, and batch systems. It separates application-specific goals and evidence from a deterministic Gatekeeper and a bounded multi-agent control flow.

The current hardening pass is intentionally non-architectural. Relative to commit `405166d9041b5460a6612c4896be591f5ec07e4c`, it should only add:

- end-to-end and negative Fallback tests;
- an independent `ubuntu-latest` Outcome Workflow CI job;
- this read-only review pack.

It must not change Profile Schema v1.1, Gatekeeper behavior, example Profile semantics, template contents or manifest, Pokemon AI application code, PR #214, or `experiments/golden_canonical_hash.py`.

## Architecture to verify

The claimed architecture has four separable parts:

1. Control plane: the opt-in Skill and workflow documents define roles, bounded phases, review gates, and release boundaries.
2. Data plane: a strict App Profile identifies the objective, immutable baseline, cycle, fixed Primary/Fallback candidates, evaluation targets, metrics, segments, permissions, and limits. External Evidence Bundles carry measurements.
3. Decision plane: `tools/outcome_gatekeeper.py` validates Profile/Evidence identity and deterministically returns `PASS`, `PASS_TO_CONFIRMATION`, `FAIL`, `INSUFFICIENT_EVIDENCE`, or `BLOCKED`.
4. Distribution plane: `template/multi-agent-workflow/` mirrors the generic components and protects package integrity through `manifest.json` and the template verifier.

The external Evaluator is not implemented by the Gatekeeper. It is responsible for executing measurements and producing Evidence, including `delta_stats`.

## Trust boundary to verify

Inputs crossing into the Gatekeeper are strict JSON data. Review these claimed boundaries against the implementation:

- Profile and Evidence strings are data and must never be executed as commands, modules, URLs, or scripts.
- External Evaluator output is not trusted merely because it is well-formed; identity, immutable artifact binding, dataset, protocol, uncertainty, stage, cycle, role, and candidate checks must fail closed.
- The Gatekeeper should use only the Python standard library and should not run evaluators, subprocesses, network calls, Git commands, or file writes.
- `delta_stats` is supplied by the external Evaluator. The Gatekeeper must not synthesize delta confidence intervals from candidate and baseline intervals.
- A Gatekeeper verdict reports eligibility only. It does not commit, push, open a PR, mark a PR ready, or merge.
- `merge` eligibility remains false. Draft removal and merge remain outside this review and require later explicit authorization after heterogeneous review.

## Schema v1.1 review map

The Profile is claimed to require exactly these top-level namespaces:

- `schema_version`, `profile_id`, `profile_version`, `status`;
- `applicability`, `objective`, `baseline`, `cycle`;
- `evaluation_targets`, `segments`, `metrics`, `stages`, `tournament`;
- `change_scope`, `permissions`, `reporting`;
- `rejected_hypothesis_memory`, `unresolved_unknowns`.

Key v1.1 contracts to verify:

- artifact bindings contain `artifact_id` plus exactly one of `immutable_ref` or lowercase SHA-256;
- the Profile fixes `cycle_id`, Primary candidate ID, and optional Fallback candidate ID;
- Evidence fixes stage, candidate role, Evidence round, candidate/baseline bindings, evaluation target, dataset, protocol, uncertainty, and metric/segment cells;
- every cell includes externally generated `baseline_stats`, `candidate_stats`, and `delta_stats`;
- permission dependency contradictions and case-insensitive allowed/prohibited path overlap fail as `BLOCKED`;
- shipped Profiles remain `example_only` and cannot be evaluated as active Profiles.

Do not propose Schema changes in this review. Report any issue that genuinely requires a Schema or Gatekeeper redesign as a blocking finding for a later design phase.

## State transition to verify

```text
Primary Screening
  BLOCKED ------------------------------> STOP
  INSUFFICIENT_EVIDENCE ----------------> same candidate / bounded evidence only
  FAIL guardrail or catastrophic -------> STOP; no Fallback
  FAIL primary criterion only ----------> pre-fixed Fallback may be evaluated once
  PASS_TO_CONFIRMATION -----------------> Primary Confirmation

Fallback Screening (requires Primary failure Evidence)
  BLOCKED / INSUFFICIENT / FAIL --------> STOP
  PASS_TO_CONFIRMATION -----------------> Fallback Confirmation

Primary or Fallback Confirmation
  any identity/binding mismatch --------> BLOCKED
  FAIL / INSUFFICIENT ------------------> no release eligibility
  PASS ---------------------------------> commit=true, push=true,
                                           pull_request=true, merge=false
```

For the Fallback path, verify that the same Fallback artifact is used for Screening and Confirmation, the Primary failure is limited to a Primary criterion, and the pre-fixed Fallback cannot be replaced by the Primary artifact or another candidate.

## Previous findings and claimed changes to inspect

| Previous independent finding | Claimed implementation area | What Claude must verify in the diff |
|---|---|---|
| Permission contradictions and allowed/prohibited path conflicts were not fail-closed | Profile validation and Gatekeeper tests | Dependency contradictions and same/ancestor/descendant path overlap, including case-only overlap, return `BLOCKED` |
| Baseline/candidate Evidence was not tied to immutable artifacts | Schema v1.1 validation and Evidence checks | Exactly-one immutable locator, Profile baseline equality, Screening/Confirmation candidate equality, and Primary/Fallback distinctness |
| Gatekeeper synthesized delta confidence data | Evidence cell validation and criterion evaluation | `delta_stats` is required and consumed directly; no interval synthesis remains |
| Primary/Fallback, Cycle ID, and Evidence round were not fixed | Profile `cycle`, Evidence identity, fallback authorization | Fixed IDs/role/cycle/round bounds and authorizing Primary failure Evidence are enforced |
| Pokemon Profile omitted Mega Starmie | root/template Pokemon example Profiles | Segment and relevant criteria/catastrophic criteria include `opponent-megastarmie` |
| Gatekeeper/template tests were absent from Actions | `.github/workflows/tests.yml` | An independent Linux job runs all three Outcome Workflow commands without depending on the application test job |

The word "claimed" is deliberate. A prior Codex audit result is not evidence that a row is resolved.

## Known limitations

- Heterogeneous Claude review is pending; this document does not satisfy that gate.
- Shipped Profiles are illustrative `example_only` fixtures, not production thresholds or active evaluation authorization.
- The repository does not ship a production external Evaluator for every target application.
- Evidence round continuity and missing-round detection belong to the external Evidence ledger; the Gatekeeper validates the supplied round label and configured bound.
- The Fallback path permits only the pre-fixed candidate and requires the Primary failure Evidence supplied to the same evaluation call; it does not maintain a persistent workflow ledger.
- Linux CI covers only the Outcome Workflow tests and template integrity. It does not assert Linux support for the Pokemon AI application.
- Template portability still depends on adoption review in the target repository.
- A passing test suite cannot establish that thresholds, datasets, or external measurements are scientifically valid.

## Read-only review checklist

- [ ] Read repository rules and confirm the review is read-only.
- [ ] Inspect the complete PR diff against `main`, not only this pack.
- [ ] Inspect the hardening delta from `405166d9041b5460a6612c4896be591f5ec07e4c` and confirm it is tests/CI/docs only.
- [ ] Confirm root/template mirrors and manifest hashes are consistent.
- [ ] Confirm Schema/Profile/Gatekeeper implementation is unchanged by the hardening delta.
- [ ] Trace the Primary and Fallback Screening/Confirmation paths directly in `evaluate()`.
- [ ] Verify all requested Fallback negative substitutions return `BLOCKED`.
- [ ] Verify `commit`, `push`, and `pull_request` become eligible only after Confirmation `PASS`, while `merge` remains false.
- [ ] Check Profile/Evidence parsing, canonical digest, artifact identity, dataset/protocol, and permission/path fail-closed behavior.
- [ ] Check that Gatekeeper imports/calls cannot execute Profile strings or mutate repository/external state.
- [ ] Confirm Pokemon AI application and protected submission files are absent from the PR diff.
- [ ] Confirm PR #214 and `experiments/golden_canonical_hash.py` are absent from the PR history/diff.
- [ ] Inspect the actual GitHub Actions run for the independent Linux job.
- [ ] Report Blocker, Major, Minor, and Test-gap findings with file/line evidence; do not rely on Codex audit labels.
- [ ] Confirm PR #215 remains Draft and Claude review remains pending until this independent review is actually completed.

## Exact review and test commands

Run from the repository root in a disposable read-only checkout where possible:

```bash
git fetch origin main
gh pr view 215 --json url,state,isDraft,baseRefName,headRefName,headRefOid
gh pr diff 215
git diff --stat origin/main...HEAD
git diff 405166d9041b5460a6612c4896be591f5ec07e4c...HEAD
git diff --exit-code 405166d9041b5460a6612c4896be591f5ec07e4c...HEAD -- tools/outcome_gatekeeper.py template/multi-agent-workflow/tools/outcome_gatekeeper.py profiles/outcome template/multi-agent-workflow/examples/app-profiles template/multi-agent-workflow/manifest.json

python -B -m unittest experiments.test_outcome_gatekeeper -v
python -B -m unittest discover -s experiments -p "test_verify_workflow_template.py" -v
python -B template/multi-agent-workflow/tools/verify_workflow_template.py source-integrity
git diff --check origin/main...HEAD

gh pr checks 215
git status --short --branch
```

Expected results written here are only hypotheses to test: all commands should complete successfully, the hardening protected-path diff should be empty, the independent Linux job should pass, and the PR should remain Draft. Any observed disagreement must be reported from the actual output.
