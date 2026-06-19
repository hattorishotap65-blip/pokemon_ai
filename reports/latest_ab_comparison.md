# A/B Anomaly Comparison

Generated: 2026-06-19 08:40 UTC

## Decision

**reject**

## Summary

- anomalies_total: 158 -> 263 (+105)
- critical: 0 -> 0 (0)
- high: 0 -> 1 (+1)
- medium: 0 -> 1 (+1)
- low: 158 -> 261 (+103)
- games: 30 (before) / 50 (after)
- confidence: medium

## Worsened

- attack_available_but_no_attack: 0 -> 1 (+1)
- ability_without_followup_attack: 0 -> 1 (+1)
- best_damage_attacker_not_selected: 158 -> 261 (+103)

## Reasons

- Total anomalies increased (+105) with no severity improvement.

## Recommendation

Candidate should be rejected — severity increased.
