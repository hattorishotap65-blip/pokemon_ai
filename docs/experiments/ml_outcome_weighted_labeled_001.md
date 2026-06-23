# ML Outcome-Weighted with Labeled Rewards 001

## Purpose

#141 で results CSV から win/loss reward を付与できるようになった。
今回はラベル付きデータで outcome-weighted training を再実行し、miss_KO 改善を確認する。

## No Behavior Change

policy.py / submission.tar.gz は一切変更していない。ML は shadow mode のみ。

## Data

| Set | Games | Matched | Win | Loss | Candidates | Decisions |
|-----|-------|---------|-----|------|------------|-----------|
| Train 50g | 50 | 50 (100%) | 29 | 21 | ~44k | ~9.6k |
| Eval 100g | 100 | 100 (100%) | 63 | 37 | 83,782 | 18,238 |

## Weighting Rule

| Condition | Weight |
|-----------|--------|
| selected=1, reward=1.0 (win) | 2.0 |
| selected=1, reward=0.0 | 1.0 |
| selected=1, reward=-1.0 (loss) | 0.5 |
| selected=0 | 1.0 |

## Results (100g eval, 18,238 decisions)

| Metric | B: No-Rule Imitation | C: No-Rule OW (labeled) |
|--------|---------------------|-------------------------|
| **Top1 agreement** | 71.9% | **72.0%** |
| **Top3 agreement** | 88.1% | **88.4%** |
| ML End top1 | 393 | 393 |
| ML End+legal_attack | **0** | **0** |
| ML miss KO | 202 | 202 |
| ML zero_damage | **0** | **0** |

## Comparison Across PRs

| PR | Mode | Top1 | Top3 | miss_KO | End+legal | zero_dmg |
|----|------|------|------|---------|-----------|----------|
| #138 | Full | 100% | 100% | 4-9 | 0 | 0 |
| #139 | No-rule | 71.5% | 87.8% | 223 (1.1%) | 0 | 0 |
| #140 | No-rule OW (no labels) | 77.8% | 91.8% | 199 | 0 | 0 |
| **#142** | **No-rule OW (labeled)** | **72.0%** | **88.4%** | **202 (1.1%)** | **0** | **0** |

## Findings

### Outcome weighting effect is minimal

With real labels (win=2.0, loss=0.5), Top1 improved by +0.1pp (71.9→72.0),
Top3 by +0.3pp (88.1→88.4). miss_KO is identical at 202.

The linear model cannot meaningfully leverage win/loss signals because:
1. Self-play actions are similar in winning and losing games
2. The reward signal is game-level, not action-level
3. A linear model lacks capacity to learn action-outcome relationships

### Safety maintained

End+legal_attack=0, zero_damage=0 across all variants.

## Decision

**Outcome weighting with linear model has negligible effect.**

The linear ranker is at its ceiling (~72% no-rule agreement).
Further improvement requires either:
1. Non-linear model (tree-based or neural)
2. Action-level reward (credit assignment)
3. Richer features (predicted_damage, hand_composition)

## Next Steps

1. **Feature enrichment**: add predicted_damage, hand energy count, bench HP distribution
2. **Non-linear model**: if feature enrichment alone doesn't push past 80%
3. **Action-level credit assignment**: for meaningful outcome weighting
4. Runtime default unchanged, ML not enabled
