# energy_attack_enablement_bonus=200.0 — 200g Validation

## Setup

| | Value | Games |
|-|-------|-------|
| **Baseline** | energy_attack_enablement_bonus=**300.0** | 200 |
| **Candidate** | energy_attack_enablement_bonus=**200.0** | 200 |

All other weights fixed at stable baseline.

## Consistency Across All Scales

| Stage | 200.0 vs baseline 300.0 |
|-------|-------------------------|
| 30g | **-10.2%** |
| 50g | **-15.0%** |
| **200g** | **-21.0%** |

**Improvement strengthens at larger scales.** Same pattern as attack_suppress_penalty.

## 200g Results

| Config | /game | Delta | vs Baseline | Safety |
|--------|-------|-------|-------------|--------|
| Baseline (300.0) | 6.61 | - | - | all 0 |
| **Candidate (200.0)** | **5.22** | **-1.39** | **-21.0% better** | all 0 |

## Safety

Both baseline and candidate: safety all 0.

## Decision

**ACCEPT.** Consistent improvement across 30g/50g/200g with safety maintained.

## Conclusion

- energy_attack_enablement_bonus=200.0 is recommended for adoption
- Improvement is consistent and strengthening: -10% → -15% → -21%
- Next step: create adoption PR to change data/weights.json from 300.0 to 200.0
- After adoption: smoke check + submission.tar.gz update

## weights.json

**Restored to 300.0. Adoption in separate PR.**
