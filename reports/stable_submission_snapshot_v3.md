# Stable Submission Snapshot v3

## Submission Info

| Item | Value |
|------|-------|
| Date | 2026-06-22 |
| Base commit | `9f3101d` (merge PR #86) |
| Submission PR | #86 |
| Size | 558 KB |
| Runtime check | Submitted environment startup confirmed |

## Included Improvements

| PR | Description |
|----|-------------|
| #75 | feat: adopt legal_attack_score 250 |
| #76 | docs: smoke check legal_attack_score 250 |
| #77 | chore: update submission after legal_attack_score 250 |
| #80 | feat: empty bench loss prevention + final prize survival |
| #82 | feat: winning attack guard |
| #83 | feat: low HP bench liability + spread threat + Poffin diversity |
| #84 | docs: smoke check low HP bench liability |
| #85 | chore: gitignore intermediate reports |
| #86 | chore: update submission |

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
| legal_attack_score | 250.0 |

## Smoke Check Results

### PR #81 (immediate loss prevention)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies/g | 5.83 |
| attack_available_but_no_attack | 0 |
| end_when_attack_available | 0 |
| retreat_when_attack_available | 0 |
| ability_without_followup_attack | 0 |

### PR #84 (low HP bench liability)

| Metric | Value |
|--------|-------|
| Games | 30 |
| Errors | 0 |
| Timeouts | 0 |
| anomalies/g | 5.80 |
| attack_available_but_no_attack | 0 |
| end_when_attack_available | 0 |
| retreat_when_attack_available | 0 |
| ability_without_followup_attack | 0 |

## Previous Stable

- v2.0-stable (energy_attack_enablement_bonus=200.0, legal_attack_score=250.0)
