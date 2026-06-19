# A/B Anomaly Comparison

Generated: 2026-06-19 10:56 UTC

## Decision

**human_review**

## Summary

- anomalies_total: 257 -> 232 (-25)
- critical: 0 -> 0 (0)
- high: 0 -> 1 (+1)
- medium: 0 -> 1 (+1)
- low: 257 -> 230 (-27)
- games: 50 (before) / 50 (after)
- confidence: high

## Improved

- best_damage_attacker_not_selected: 257 -> 230 (-27)

## Worsened

- attack_available_but_no_attack: 0 -> 1 (+1)
- ability_without_followup_attack: 0 -> 1 (+1)

## Reasons

- Improvement and worsening are mixed across metrics.

## Recommendation

Mixed signals — human review recommended.
