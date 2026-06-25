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
    --report experiments/learning/reports/latest_report.md
```

## Scope

- Target deck: Raging Bolt ex + Teal Mask Ogerpon ex
- Input: manually created JSONL logs (not connected to PTCG-sim yet)
- Model: linear weights * features (no neural network)
- No changes to main.py, deck.csv, submission.tar.gz, or agent/
