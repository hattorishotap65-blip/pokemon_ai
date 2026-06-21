# Submitted Stable Snapshot — 2026-06-21

## Status

This document records the current known-good version after the `energy_attack_enablement_bonus` adoption series.

- Submission status: submitted
- Runtime status: confirmed to start in the target environment
- Source baseline: latest stable after PR #65
- Purpose: keep a rollback reference before any further experiments

## Relevant PRs

| PR | Purpose | Status |
|----|---------|--------|
| #63 | Adopt `energy_attack_enablement_bonus=200.0` | merged |
| #64 | Post-adoption smoke check | merged |
| #65 | Rebuild `submission.tar.gz` after adoption | merged and submitted |

## Stable Weights

| Parameter | Value |
|-----------|-------|
| `retreat_to_better_attacker_bonus` | `1400.0` |
| `attack_suppress_penalty` | `-40.0` |
| `advantage_weight` | `0.4` |
| `energy_to_plan_bonus` | `5.0` |
| `energy_to_plan_bonus_no_need` | `2.0` |
| `voltorb_ko_attack_bonus` | `1000.0` |
| `voltorb_damage_scaling` | `0.8` |
| `energy_attack_enablement_bonus` | `200.0` |

## Validation Summary

| Stage | Result vs baseline 300.0 | Decision |
|-------|---------------------------|----------|
| 30g | approximately `-10%` | promote |
| 50g | approximately `-15%` | promote |
| 200g | approximately `-21%` | accept |

Post-adoption smoke check:

- Tests: `352/352 pass`
- Smoke: `30g`
- Errors: `0`
- Timeouts: `0`
- Safety: all 0

## Artifact

`submission.tar.gz` was rebuilt after adoption in PR #65 and confirmed to start in the target environment.

## Guardrail

Future experiments should keep this snapshot as the rollback reference.
