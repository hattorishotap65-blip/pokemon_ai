# legal_attack_score=250.0 — 200g Validation

## Setup

| | Value | Games |
|-|-------|-------|
| **Baseline** | legal_attack_score=**150.0** | 200 (4x50g) |
| **Candidate** | legal_attack_score=**250.0** | 200 (4x50g) |
| Matched game sets | **Yes** | |

## Consistency

| Stage | 250.0 vs baseline 150.0 |
|-------|-------------------------|
| 30g | **-9.4%** |
| 50g | **-16.6%** |
| **200g** | **-7.4%** |

## 200g Results

| Config | Anomalies | /game | Safety |
|--------|-----------|-------|--------|
| Baseline (150.0) | 1060 | 5.30 | all 0 |
| **Candidate (250.0)** | **982** | **4.91** | all 0 |

| Metric | Value |
|--------|-------|
| Delta | -0.39 |
| vs Baseline | **-7.4% better** |
| Decision | **ACCEPT** |

## Batch Details

| Batch | Baseline | Candidate | Winner |
|-------|----------|-----------|--------|
| 1 (g26000-26049) | 290 (5.80) | 244 (4.88) | candidate |
| 2 (g26100-26149) | 291 (5.82) | 212 (4.24) | candidate |
| 3 (g26200-26249) | 249 (4.98) | 247 (4.94) | tie |
| 4 (g26300-26349) | 230 (4.60) | 279 (5.58) | baseline |

Candidate won 2/4 batches, tied 1, lost 1. Overall improvement consistent.

## Decision

**ACCEPT.** Consistent improvement across 30g/50g/200g. Safety all 0.

## Next Step

Create adoption PR: legal_attack_score 150.0 → 250.0

## weights.json

**Restored to 150.0. Adoption in separate PR.**
