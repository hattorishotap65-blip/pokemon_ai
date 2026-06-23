# ML Nonlinear Shadow Scoring 001

## Purpose

Linear ranker hit ~78% ceiling. Evaluate decision tree on existing 30 features.

## No Behavior Change

policy.py / submission.tar.gz unchanged. ML is shadow mode only.

## Model

- Type: Pure-Python DecisionTreeRanker (no sklearn)
- max_depth=6, min_samples_leaf=20
- Gini impurity, greedy splits

## Data

| Set | Games | Matched | Win | Loss | Candidates | Decisions |
|-----|-------|---------|-----|------|------------|-----------|
| Train | 50 | 50 (100%) | 30 | 20 | ~45k | ~10k |
| Eval | 100 | 100 (100%) | 60 | 40 | 94,916 | 20,493 |

## Results (100g eval, 20,493 decisions)

| Metric | A: Linear (30 feat) | B: Decision Tree (30 feat) |
|--------|--------------------|-----------------------------|
| **Top1 agreement** | 77.3% | **87.8%** (+10.5pp) |
| **Top3 agreement** | 90.4% | **99.3%** (+8.9pp) |
| ML End top1 | 383 | 806 |
| ML End+legal_attack | **0** | **0** |
| **ML miss KO** | 222 (1.1%) | **3 (0.01%)** |
| ML zero_damage | **0** | **0** |

## Comparison Across All PRs

| PR | Model | Features | Top1 | Top3 | miss_KO | unsafe |
|----|-------|----------|------|------|---------|--------|
| #138 | Linear | Full 32 | 100% | 100% | 4-9 | 0 |
| #139 | Linear | No-rule 30 | 71.5% | 87.8% | 223 | 0 |
| #142 | Linear | No-rule OW | 72.0% | 88.4% | 202 | 0 |
| #143 B | Linear | No-rule 30 | 77.8% | 91.1% | 197 | 0 |
| #143 C | Linear | Enriched 39 | 71.7% | 87.8% | 212 | 0 |
| **#144** | **DecisionTree** | **No-rule 30** | **87.8%** | **99.3%** | **3** | **0** |

## Key Findings

### Decision tree dramatically improves over linear

- Top1: +10.5pp (77.3% → 87.8%)
- Top3: +8.9pp (90.4% → 99.3%)
- miss_KO: -99% (222 → 3)

### Safety fully maintained

- End+legal_attack: 0
- zero_damage: 0
- miss_KO: 3/20,493 = 0.01%

### ML End top1 increased (383 → 806)

Tree model predicts End more often, but never when legal attack exists.
This suggests the tree learned the correct context for ending turns.

## Decision

**Decision tree is highly promising for hybrid mode.**

- Top1 87.8% with no rule_score features
- miss_KO reduced to near-zero (3/20,493)
- Safety fully maintained
- Next: safety gate design → hybrid 10% evaluation

## Next Steps

1. **Safety gate design**: ensure ML cannot select End when legal attack exists
2. **Hybrid 10% evaluation**: add small ML bonus to rule_score, evaluate in 100g
3. **Enriched features with tree**: #143 enriched features may help tree (unlike linear)
4. **Overfitting check**: evaluate on different data splits
