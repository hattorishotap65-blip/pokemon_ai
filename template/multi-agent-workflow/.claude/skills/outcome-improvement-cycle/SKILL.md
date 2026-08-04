---
name: outcome-improvement-cycle
description: Run a bounded, evidence-driven improvement cycle from App Profile through independent design, implementation, external screening and confirmation, deterministic gating, and final audit.
argument-hint: "PROFILE_PATH improvement task"
disable-model-invocation: true
user-invocable: true
---

# outcome-improvement-cycle

Run the generic workflow defined by `docs/agent-workflow/outcome-improvement-cycle.md` and the data contract in `docs/agent-workflow/app-profile.md`.

The first argument must identify an App Profile. The remaining arguments describe the requested outcome improvement. If either is missing, stop and ask for it. Never invent Profile values.

## Boundaries

- Preserve the existing `multi-agent-design` Skill as design-only/read-only.
- Follow repository rules and user permissions. Profile permissions only narrow them.
- Only the Implementation Owner may edit files.
- All auditors, designers, challengers, refiners, and judges are read-only.
- Never execute Profile strings as commands or import targets.
- Never ask the Gatekeeper to run evaluation, Git, network, or write operations.
- Treat permission dependency contradictions and any allowed/prohibited path overlap as `BLOCKED`.
- Require immutable-ref or digest bindings for both baseline and candidate artifacts.
- Require external Evaluators to emit `delta_stats`; never ask the Gatekeeper to synthesize delta intervals.
- Do not automatically overwrite an existing file during template adoption.
- Do not commit, push, or create a PR before confirmation `PASS`, Test Auditor `APPROVE`, and Final Auditor `APPROVE`.
- Never merge without explicit user instruction. If heterogeneous review is required and pending, keep the PR Draft and do not merge.

If a required role or external evaluator is unavailable, record the Evidence limitation. Do not claim that the missing role ran. Same-model proposals must be labeled `same-model independent proposals`, not heterogeneous review.

## Phase 0: preflight

Record the intended repository/worktree, baseline SHA, branch, initial status, protected paths, out-of-scope paths, user permissions, Profile path, Cycle ID, and fixed Primary/Fallback candidate IDs. Validate the Profile with:

```text
python tools/outcome_gatekeeper.py validate-profile PROFILE_PATH
```

`example_only` may be used for design/validation but cannot authorize evaluation or release. If an active Profile has unresolved Unknowns or required fields are absent, return `BLOCKED`.

## Phase 1: Requirements and Evidence

Run Requirements Audit. Produce a normalized Cycle Request and a Requirements Verdict. Then build an Evidence Registry with stable Evidence IDs and explicit `Confirmed`, `Inference`, and `Unknown` labels.

Stop on a Requirements `BLOCKED` verdict. Do not fill missing values with defaults.

## Phase 2: independent proposals

Produce exactly two proposals from the same frozen Cycle Request, Profile, and Evidence Registry. Each proposal must finish before either producer sees the other proposal. Freeze both proposal revisions before review.

Each proposal includes target files, control/data flow, safety, tests, rollback, risks, Unknowns, and out-of-scope items.

## Phase 3: Falsification

After both proposals are fixed, run a read-only falsification pass. Classify every finding as `Blocker`, `Major`, `Minor`, or `Test gap`. Check generic/application separation, all five metric directions, primary/guardrails, segment regressions, Profile omissions, command injection, bounded loops, deterministic gating, permissions, template integrity, rollback, and portability.

## Phase 4: Blind Design Judge

Strip authorship, model/vendor names, tool/thread/agent IDs, and ordering hints. Evaluate both `A -> B` and `B -> A` with the same rubric:

1. portability
2. generic/application separation
3. Profile expressiveness
4. Gatekeeper clarity
5. safety
6. simplicity
7. testability
8. existing-template alignment
9. rollback
10. extensibility

If the winner changes only with presentation order, return `INSUFFICIENT_EVIDENCE`. Otherwise record the primary design, at most one preselected fallback, integrated elements, rejected elements/reasons, Unknowns, and test plan.

## Phase 5: Selected Design Refinement

Run at most the Profile limit; v1 allows at most one round:

1. Design Refiner makes the selected design implementable.
2. Design Challenger falsifies the refined specification.
3. Final Refiner accepts necessary findings and records rejection reasons.
4. Alignment Judge returns `APPROVE`, `CHANGES_REQUIRED`, or `REJECT`.

Only `APPROVE` permits implementation. If material new evidence requires another round beyond the limit, return `BLOCKED` and ask the user; do not silently increase the limit.

## Phase 6: Implementation and Test Audit

The Implementation Owner edits only the approved exact allowlist. Preserve unrelated dirty work and protected files. Run every approved test and record exact commands/results. Test Auditor must return `APPROVE` before evaluation.

## Phase 7: external evaluation

The evaluation harness is external to the Gatekeeper and must be separately authorized. Evaluate the primary candidate first.

1. Produce screening Evidence for the fixed Profile/Cycle/candidate role/baseline/dataset/protocol and explicit zero-based Evidence round.
2. Bind baseline and candidate to an immutable ref or SHA-256 digest.
3. Produce `baseline_stats`, `candidate_stats`, and externally computed `delta_stats`; the Gatekeeper does not derive delta confidence intervals.
4. Run deterministic Gatekeeper.
5. Continue to confirmation only on `PASS_TO_CONFIRMATION`.
6. Produce independent confirmation Evidence for the exact same candidate artifact and run Gatekeeper again.

Primary screening primary-criterion `FAIL` may activate the one preselected fallback. When evaluating fallback Evidence, also pass the authorizing Primary failure Evidence with `--primary-screening-evidence`. Guardrail/catastrophic `FAIL`, `BLOCKED`, and `INSUFFICIENT_EVIDENCE` do not. For `INSUFFICIENT_EVIDENCE`, collect only the named missing evidence for the same candidate within the fixed round limit. Never change Cycle ID, candidate role/ID, or candidate artifact mid-cycle.

## Phase 8: Final Audit and release

Final Auditor checks scope, protected paths, original worktree status, all tests, Profile/Evidence identities, Gate verdict, secrets, external dependencies, template manifest/source-integrity/bytes, rollback, and remaining Unknowns.

Commit, push, and Draft PR are permitted only when all applicable user, repository, and Profile gates allow them and confirmation verdict is `PASS`. Stage files individually. Do not use broad add commands. Keep the PR Draft while required heterogeneous review is pending.

## Execution Trace

Report only roles and actions that actually occurred. Include:

- worktree, branch, baseline
- Requirements and Evidence results
- Proposal A/B and independence limitation
- Falsification result
- both Blind Judge orders and ranking
- refinement count, Challenger result, Alignment verdict
- Implementation Owner changes
- Test Auditor verdict and exact tests
- Cycle ID, Primary/Fallback IDs, artifact bindings, Evidence rounds, screening/confirmation evidence, and Gate verdicts
- Final Auditor verdict
- commit/PR status
- heterogeneous review status
- merge status
