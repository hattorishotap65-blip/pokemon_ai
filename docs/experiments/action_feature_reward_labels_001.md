# Action Feature Reward Labels 001

## Purpose

#140 で outcome-weighted training を試みたが、self-play ログの reward が全て 0.0 (unknown)
だったため効果がなかった。今回は results CSV を game_id で join し、正しい win/loss reward
を付与できるようにする。

## Background

- Self-play per-decision ログには game_result が書き込まれない
- run_matches_real.py の results CSV に winner (p0/p1) が記録される
- game_id = start_game + (csv_game - 1) で結合可能

## Reward Definition

| Winner | game_result | reward |
|--------|-----------|--------|
| p0 | win | 1.0 |
| p1 | loss | -1.0 |
| (empty) | draw | 0.0 |
| timeout | timeout | -1.0 |
| error | error | -1.0 |
| (no CSV) | unknown | 0.0 |

## Commands

```bash
# Run games
python experiments/action_feature_logging.py \
    --n 50 --start-game 170000 --run-games --use-wsl \
    --output artifacts/action_features_50g_raw.jsonl

# Re-process with results CSV
python experiments/action_feature_logging.py \
    --n 50 --start-game 170000 \
    --output artifacts/action_features_50g_labeled.jsonl \
    --results-csv logs/real_20260623_204521.csv
```

## Results (50g)

| Metric | Without CSV | With CSV |
|--------|-------------|----------|
| Games | 50 | 50 |
| Matched games | 0 | **50** |
| Unmatched games | 50 | **0** |
| Match rate | 0% | **100%** |
| Decisions | 10,372 | 10,372 |
| Candidates | 47,614 | 47,614 |

### Reward Distribution (with CSV)

| Result | Games | Reward |
|--------|-------|--------|
| win | **25** | 1.0 |
| loss | **25** | -1.0 |
| draw | 0 | 0.0 |
| unknown | 0 | 0.0 |

## Verification

- reward=0.0 だけの問題: **解消** (win: 1.0, loss: -1.0 が両方存在)
- match rate: **100%**
- decision_id: 維持
- policy.py: 変更なし
- errors/timeouts: 0

## Results CSV Format

| Column | Description |
|--------|-------------|
| game | 1-based game index |
| winner | p0 / p1 |
| selections | total selections |
| score | +10 (win) / -10 (loss) |

Join key: `game_id = start_game + game - 1`

## No Behavior Change

policy.py / submission.tar.gz / configs は一切変更していない。

## Next Steps

1. **Re-run outcome-weighted training** with labeled data
2. Compare miss_KO rate: no-rule imitation vs outcome-weighted with real labels
3. If miss_KO improves, evaluate for hybrid mode candidacy
