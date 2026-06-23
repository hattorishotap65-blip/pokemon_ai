# ML Outcome-Weighted Shadow Scoring 001

## Purpose

#139 の no-rule ML (Top1 71.5%) に outcome weighting を追加し、
勝ちに寄与する action をより高く評価できるか検証する。

## No Behavior Change

policy.py の行動選択ロジックは一切変更していない。
submission.tar.gz 更新なし。ML は shadow mode のみ。

## Weighting Rule

| Condition | Weight |
|-----------|--------|
| selected=1, reward>0 (win) | 2.0 |
| selected=1, reward=0 (unknown) | 1.0 |
| selected=1, reward<0 (loss) | 0.5 |
| selected=0 | 1.0 |

## Results (100g eval, 20,486 decisions)

| Metric | B: No-Rule Imitation | C: No-Rule Outcome-Weighted |
|--------|---------------------|-----------------------------|
| Top1 agreement | 77.8% | 77.8% |
| Top3 agreement | 91.8% | 91.8% |
| ML End+legal_attack | **0** | **0** |
| ML zero_damage | **0** | **0** |
| ML miss KO | 199 (0.97%) | 199 (0.97%) |

## Key Finding: Outcome Weighting Has No Effect

B and C produce **identical results** because all training data has
`reward=0.0` (unknown game result).

Self-play logs do not record win/loss per decision — the game result
is determined externally by `run_matches_real.py` and stored in the
results CSV, not in the per-decision JSONL logs.

Without meaningful reward labels, outcome weighting cannot differentiate
winning actions from losing actions.

## Comparison with #139

| Metric | #139 (different data) | This PR (B/C) |
|--------|-----------------------|---------------|
| Top1 agreement | 71.5% | **77.8%** |
| Top3 agreement | 87.8% | **91.8%** |
| ML miss KO | 223 (1.1%) | 199 (0.97%) |
| End+legal_attack | 0 | 0 |
| zero_damage | 0 | 0 |

The improvement from 71.5% to 77.8% is due to different train/eval data
(start_game 150k vs 160k), not outcome weighting.

## Safety

| Check | Result |
|-------|--------|
| ML End + legal_attack | **0** (safe) |
| ML zero_damage top1 | **0** (safe) |
| ML miss KO | 199 (0.97%) |

Safety maintained across all variants.

## Decision

**Outcome weighting is not effective with current data pipeline.**

The self-play logger does not write game_result to per-decision entries.
To make outcome weighting work, one of the following is needed:

1. **Join results CSV by game_id**: post-process action features JSONL with
   game results from `run_matches_real.py` results CSV
2. **Log game result in decisions**: modify logger to include final game
   result in every decision entry (requires second pass or deferred write)

## Next Steps

1. **Fix reward labels**: join results CSV by game_id in action_feature_logging.py
2. **Re-run outcome-weighted training** with actual win/loss rewards
3. **Then evaluate** whether miss_KO decreases and agreement improves
4. Feature improvement remains a parallel track
5. Runtime default unchanged
