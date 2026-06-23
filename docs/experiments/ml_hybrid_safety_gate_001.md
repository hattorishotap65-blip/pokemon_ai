# ML Hybrid Safety Gate Evaluation 001

## Purpose

#144 DecisionTree shadow が Top1 87.8%, miss_KO 3 と有望。
Safety gate 付き hybrid scoring を offline 評価する。

## No Behavior Change

policy.py / submission.tar.gz 一切変更なし。ML は offline eval のみ。

## Safety Gates

| Gate | Rule |
|------|------|
| G1 | End + legal_attack → ML bonus=0 |
| G2 | zero_damage_attack → ML bonus=0 |
| G3 | can_ko available + non-attack → ML bonus=0 |
| G5 | Error/missing → rule_score only |

## Hybrid Formula

`hybrid_score = rule_score + bonus_ratio * normalized_ml_score`

normalized_ml_score: 0~1 within decision. Safety-gated candidates get bonus=0.

## Data

| Set | Games | Matched | Win | Loss |
|-----|-------|---------|-----|------|
| Train | 50 | 50 (100%) | 28 | 22 |
| Eval | 100 | 100 (100%) | 50 | 50 |

## Results (100g eval, 18,769 decisions)

| Metric | Bonus=0.1 | Bonus=1.0 | Bonus=5.0 |
|--------|-----------|-----------|-----------|
| Rule/Hybrid agree | 100.0% | 100.0% | **99.7%** |
| Changed decisions | 1 (0.0%) | 8 (0.0%) | **55 (0.3%)** |
| End+legal_attack | **0** | **0** | **0** |
| Zero damage | **0** | **0** | **0** |
| Miss KO | 5 | 5 | 5 |
| Gate blocked | 2,035 | 2,035 | 2,035 |
| Reward delta | 0.0 | 0.0 | 0.0 |

## Key Findings

### Safety gates work perfectly

- End+legal_attack: **0** across all bonus levels
- zero_damage: **0** across all bonus levels
- miss_KO: 5 (stable, 0.03%)
- 2,035 gate blocks = safety gates correctly preventing dangerous ML proposals

### Hybrid changes are minimal but safe

- Bonus=5.0 changes 55/18,769 decisions (0.3%)
- No safety violations in changed decisions
- Reward delta = 0.0 (neutral — self-play symmetric)

### Bonus ratio needs tuning

- 0.1 is too small (1 change)
- 1.0 is still very small (8 changes)
- 5.0 starts having effect (55 changes)
- Higher bonus may change more decisions but needs careful monitoring

## Decision

**Safety gate works. Hybrid scoring is safe at tested bonus levels.**

All safety conditions met:
- End+legal_attack = 0 ✓
- zero_damage = 0 ✓
- miss_KO stable ✓
- changed rate < 1% ✓
- no reward degradation ✓

## Next Steps

1. **Real self-play evaluation**: integrate hybrid into runtime (env flag), run 100g
2. **Bonus ratio search**: try 5.0-20.0 range in self-play
3. **Gate tuning**: relax G3 (ko_available) if too aggressive
4. **Submission candidate**: if self-play hybrid improves score, create new submission
