# legal_attack_score Staged Pipeline Summary

- Parameter: **legal_attack_score**
- Baseline: **150.0**
- Initial candidates: [75.0, 100.0, 200.0, 250.0]

Note: Magneton/Magnemite evolve bonus does not exist in this deck.
Substituted with turn_rule_engine legal_attack_score (Priority B1).

## 30g

Baseline: 5.77/g

| Value | /game | vs Baseline | Safety | Decision |
|-------|-------|-------------|--------|----------|
| 75.0 | 5.90 | +2.2% worse | all_0 | reject |
| **100.0** | **5.27** | **-8.7%** | all_0 | **promote** |
| **200.0** | **5.37** | **-6.9%** | all_0 | **promote** |
| **250.0** | **5.23** | **-9.4%** | all_0 | **promote** |

Promoted to 50g: [100.0, 200.0, 250.0]

## 50g (manual re-run after pipeline timeout)

Baseline: 5.78/g

| Value | /game | vs Baseline | Safety | Decision |
|-------|-------|-------------|--------|----------|
| **100.0** | **4.14** | **-28.4%** | all_0 | **promote** |
| 200.0 | 5.60 | -3.1% | all_0 | hold (marginal) |
| **250.0** | **4.82** | **-16.6%** | all_0 | **promote** |

Promoted to 200g: [100.0, 250.0]

## Status

200g not yet run (staged pipeline timed out at 200g stage).
100.0 is the primary 200g candidate (-28% at 50g).

## Next Step

Run 200g for legal_attack_score=100.0 in next PR.

## Safety

All patterns: safety all 0 at all stages.

## weights.json

Restored to 150.0. No permanent changes.
