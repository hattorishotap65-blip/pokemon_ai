# legal_attack_score=100.0 — 200g Validation

## Setup

| | Value | Games |
|-|-------|-------|
| **Baseline** | legal_attack_score=**150.0** | 200 (4x50g) |
| **Candidate** | legal_attack_score=**100.0** | 200 (4x50g) |
| Matched game sets | **Yes** | |

## Consistency Check

| Stage | 100.0 vs baseline 150.0 |
|-------|-------------------------|
| 30g | -8.7% |
| 50g | -28.4% |
| **200g** | **+13.6% worse** |

## 200g Results

| Config | Anomalies | /game | Safety |
|--------|-----------|-------|--------|
| Baseline (150.0) | 901 | **4.50** | all 0 |
| Candidate (100.0) | 1021 | 5.11 | all 0 |

| Metric | Value |
|--------|-------|
| Delta | +0.61 |
| vs Baseline | **+13.6% worse** |
| Decision | **reject** |

## Batch Details

| Batch | Baseline | Candidate |
|-------|----------|-----------|
| 1 (g25000-25049) | 226 (4.52) | 301 (6.02) |
| 2 (g25100-25149) | 220 (4.40) | 206 (4.12) |
| 3 (g25200-25249) | 238 (4.76) | 278 (5.56) |
| 4 (g25300-25349) | 217 (4.34) | 236 (4.72) |

Candidate was better in batch 2 only. Inconsistent across batches.

## Decision

**REJECT.** legal_attack_score=100.0 rejected at 200g.
legal_attack_score=150.0 remains the baseline.
250.0 remains an optional 200g candidate if we want to fully close this parameter.

## weights.json

**Restored to 150.0. No permanent changes.**
