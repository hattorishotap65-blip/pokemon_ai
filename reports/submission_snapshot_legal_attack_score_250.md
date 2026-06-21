# Stable Snapshot: legal_attack_score=250.0

## Status

**Stable / Submitted / Runtime confirmed**

## Changes

legal_attack_score adopted at 250.0 (was 150.0).
Validated: 30g=-9.4%, 50g=-16.6%, 200g=-7.4%. Safety all 0.

## Current Weights

| Parameter | Value |
|-----------|-------|
| advantage_weight | 0.4 |
| energy_to_plan_bonus | 5.0 |
| energy_to_plan_bonus_no_need | 2.0 |
| attack_suppress_penalty | -40.0 |
| retreat_to_better_attacker_bonus | 1400.0 |
| voltorb_ko_attack_bonus | 1000.0 |
| voltorb_damage_scaling | 0.8 |
| energy_attack_enablement_bonus | 200.0 |
| evolve_first_bellibolt_bonus | 220.0 |
| evolve_first_kilowattrel_bonus | 7.0 |
| **legal_attack_score** | **250.0** |

## Smoke Check

| Metric | Value |
|--------|-------|
| Games | 30 |
| Anomalies/g | 4.87 |
| Errors | 0 |
| Timeouts | 0 |
| Safety | all 0 |

## submission.tar.gz

Updated (556 KB). Runtime startup confirmed in submission environment.

## PR History

| PR | Content |
|----|---------|
| #75 | feat: adopt legal_attack_score 250 |
| #76 | docs: smoke check |
| #77 | chore: update submission.tar.gz |
| #78 | feat: adoption flow tools |

## Previous Stable

v2.0-stable (energy_attack_enablement_bonus=200.0 adoption)
