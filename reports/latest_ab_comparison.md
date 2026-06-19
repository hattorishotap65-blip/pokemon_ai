# A/B Anomaly Comparison

Generated: 2026-06-19 02:51 UTC

## Decision

**accept**

## Summary

- anomalies_total: 25 -> 12 (-13)
- critical: 2 -> 0 (-2)
- high: 8 -> 3 (-5)
- medium: 10 -> 6 (-4)
- low: 5 -> 3 (-2)
- games: 50 (before) / 50 (after)
- confidence: high

## Improved

- attack_available_but_no_attack: 8 -> 3 (-5)
- end_when_attack_available: 2 -> 0 (-2)
- retreat_when_attack_available: 3 -> 0 (-3)
- ability_without_followup_attack: 5 -> 3 (-2)
- ko_available_but_no_attack: 2 -> 0 (-2)
- ability_breaks_attack_ready_state: 1 -> 0 (-1)

## Worsened

- overattach_to_ready_attacker: 3 -> 4 (+1)
- duplicate_stage1_search: 0 -> 1 (+1)

## Reasons

- Total anomalies decreased.
- Critical anomalies decreased.
- High severity anomalies decreased.
- Worsened metrics are minor (low/info or delta<=1).

## Recommendation

Candidate is safe to adopt.
