# PR0-A.1 Review Guide - Parameter Contract Correctness

## Scope

This review unit corrects the existing static Parameter Contract audit only.

It does not change:

- `experiments/agents/raging_bolt/main.py`
- root `main.py`
- either `params.json` or `deck.csv`
- policy scores, candidate generation, search, rollout, or selected actions
- the unrelated in-progress PR0-B replay files in the worktree

## Why this correction is required

The original audit classified every `self.p()` reference as `ACTIVE`. That is
too strong for a static scan and caused a concrete false positive:
`evaluate_state()` is called, but its return value is assigned to
`current_eval` and never read. Its 19 `eval_*` parameters therefore have no
observed effect on the selected action.

The corrected audit keeps these concepts separate:

1. code reference;
2. static return-value use;
3. current-configuration reachability;
4. runtime counterfactual evidence;
5. Live Tuning API capability and type safety.

`ACTIVE` now requires runtime counterfactual evidence that a value change
changes candidate rank or selected action. The static scanner deliberately
uses `REFERENCED_UNVERIFIED` until that evidence exists.

## Files to review

Review in this order:

1. `experiments/test_audit_parameter_contract.py`
2. `experiments/audit_parameter_contract.py`
3. `experiments/agents/raging_bolt/audit/parameter_audit_report.md`
4. the three generated JSON artifacts in the same audit directory
5. `scripts/run_all_tests.sh` and `.github/workflows/tests.yml`

`PR0_A_1_REVIEW.md` is reviewer guidance, not generated output.

## Expected findings

```text
ACTIVE=0
REFERENCED_UNVERIFIED=89
UNUSED=15
SHADOWED=19
Current-config disabled=3
Runtime override API-supported=77
Runtime override declared-type not enforced=71
Runtime override numeric-family mismatch=1
```

- All 19 `eval_*` entries are `SHADOWED` with
  `enclosing_scoring_result_is_not_consumed`.
- `se_*` weights are statically decision-relevant but remain unverified.
- `value_model_weight` is disabled by `use_value_model=false`.
- `engine_search_samples` and `endgame_samples` are disabled by the current
  `rule_ucb1_search=1` early-return path.
- Live Tuning can mutate keys present in `params.json` through `module.P`.
- The endpoint accepts both integer and non-integer numeric values without
  checking each key's base type. This does not preserve 70 integer contracts.
- `use_value_model` is also exposed, but its base boolean type is replaced by
  a numeric value, creating the one numeric-family mismatch.
- Negative `_EVAL_FEATURE_WEIGHTS` values missed by the old scanner are
  included.

## Reproduction

The worktree contains unrelated unfinished PR0-B edits to the agent. For an
isolated and reproducible review, all generated artifacts are pinned to the
last committed PR0-A source:

```text
bf194b44ac43cfc174dbc0a356e3c91e87e9bda5
```

Run:

```bash
python3 -m unittest experiments.test_audit_parameter_contract -v
python3 experiments/audit_parameter_contract.py \
  --source-ref bf194b44ac43cfc174dbc0a356e3c91e87e9bda5 \
  --check
```

Latest result:

```text
Ran 14 tests
OK
ACTIVE=0 REFERENCED_UNVERIFIED=89 EXPERIMENTAL=0 DEPRECATED=0 UNUSED=15 SHADOWED=19 hardcoded=286
```

The artifact consistency test regenerates and byte-compares all four generated
outputs. Provenance records the exact commit, raw `main.py` hash, raw
`params.json` hash, and normalized effective-parameter hash.
CI checks out full history so the pinned commit is available; shallow local
checkouts fall back only when all three recorded source hashes match.

## Review checklist

- [ ] Static references are not overclaimed as `ACTIVE`.
- [ ] A dead assigned scoring return is `SHADOWED`.
- [ ] Ternary parameter keys and negative constants are resolved.
- [ ] Direct guards and post-early-return guards are conservative.
- [ ] Unknown `unit`, `min`, `max`, and `description` stay `null`.
- [ ] Runtime override capability matches the current Live Tuning endpoint.
- [ ] Integer and boolean override type risks are visible and separate from
  decision effect.
- [ ] Generated artifacts are pinned and byte-reproducible.
- [ ] CI and the local aggregate runner execute the new tests.
- [ ] No production policy or submission file is part of this review unit.

## Known limitations and deferred work

- Return-use detection is shallow static analysis, not full data-flow or
  runtime proof.
- Only simple truthy/falsey `self.p()` guards and top-level terminating
  early-return guards are evaluated. Other paths remain unverified.
- `DUPLICATE` and `CONFLICTING_CODE_DEFAULTS` are review flags, not automatic
  proof of shadowing or permission to merge keys.
- `EXPERIMENTAL` and `DEPRECATED` are not inferred without explicit metadata.
- The hardcoded inventory includes structural constants and card IDs; entries
  are labelled `UNCLASSIFIED_NUMERIC_LITERAL` for human triage.
- Strict Telemetry completion belongs to the separate PR0-A.2 review.
- Snapshot/replay/partial-CRN work remains the separate unfinished PR0-B and
  must not be included in this review.
