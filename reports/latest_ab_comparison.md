# A/B Anomaly Comparison

Generated: 2026-06-19 13:19 UTC

## Decision

**reject**

## Summary

- anomalies_total: 295 -> 301 (+6)
- critical: 0 -> 0 (0)
- high: 2 -> 4 (+2)
- medium: 2 -> 1 (-1)
- low: 291 -> 296 (+5)
- games: 50 (before) / 50 (after)
- confidence: high

## Improved

- ability_without_followup_attack: 2 -> 1 (-1)

## Worsened

- attack_available_but_no_attack: 2 -> 3 (+1)
- retreat_when_attack_available: 0 -> 1 (+1)
- best_damage_attacker_not_selected: 291 -> 296 (+5)

## Reasons

- Total anomalies increased (+6) with no severity improvement.

## Recommendation

Candidate should be rejected — severity increased.
