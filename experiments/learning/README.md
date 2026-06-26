# Learning Scaffold MVP

## Purpose

Learn action evaluation weights from human play logs.
Train an evaluator to predict which action a human would choose,
then use those weights to improve AI decision-making.

## Architecture

```
sample_logs/*.jsonl  -->  action_features.py  -->  evaluator.py  -->  train_weights.py
                                                                          |
params/default.json  ------------------------------------------------>   |
                                                                          v
                                                              params/learned.json
                                                              reports/latest_report.md
```

## Components

| File | Purpose |
|------|---------|
| `schema.py` | Log JSONL validation |
| `action_features.py` | Action -> feature vector extraction |
| `evaluator.py` | Weighted scoring (weights * features) |
| `train_weights.py` | Perceptron-style weight updater CLI |
| `report.py` | Before/after Markdown report |

## Usage

```bash
python experiments/learning/train_weights.py \
    --logs experiments/learning/sample_logs/raging_ogerpon_sample.jsonl \
    --params experiments/learning/params/raging_ogerpon_default.json \
    --out experiments/learning/params/raging_ogerpon_learned.json \
    --report experiments/learning/reports/latest_report.md \
    --epochs 50 --lr 0.1
```

Note: CLI default is `--epochs 5 --lr 0.05`. For sample data, `--epochs 50 --lr 0.1`
produces measurable improvement (42.9% -> 57.1%).

## Loss-Aware Learning

The trainer uses a loss-aware multiplier on the learning rate:
- Wins are weighted slightly higher (x1.2)
- Losses are weighted lower (x0.7)
- Bricked games are down-weighted (x0.5)
- High-prize games (>=5) are not overly penalized (x1.1)
- Fast wins (<=5 turns) are slightly reinforced (x1.1)
- Multiplier is clamped to [0.2, 2.0]

## Scope

- Target deck: Raging Bolt ex + Teal Mask Ogerpon ex
- Input: manually created JSONL logs (not connected to PTCG-sim yet)
- Model: linear weights * features (no neural network)
- No changes to main.py, deck.csv, submission.tar.gz, or agent/
