#!/usr/bin/env bash
# Run ML hybrid bonus ratio sweep: 8 / 10 / 12 / 15
# Execute from repo root inside WSL or with --use-wsl flag.
set -euo pipefail

echo "=== ML Hybrid Bonus Sweep ==="
echo "Ratios: 8, 10, 12, 15"
echo ""

mkdir -p artifacts

# bonus=8
echo "--- bonus=8 (100g, start=260000) ---"
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=8.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 260000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus8_100g.jsonl

# bonus=10
echo "--- bonus=10 (100g, start=261000) ---"
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=10.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 261000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus10_100g.jsonl

# bonus=12
echo "--- bonus=12 (100g, start=262000) ---"
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=12.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 262000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus12_100g.jsonl

# bonus=15
echo "--- bonus=15 (100g, start=263000) ---"
POKEMON_AI_ML_HYBRID=1 POKEMON_AI_ML_BONUS_RATIO=15.0 \
  python experiments/action_feature_logging.py \
    --n 100 --start-game 263000 --run-games --use-wsl \
    --output artifacts/ml_hybrid_bonus15_100g.jsonl

echo ""
echo "=== Aggregating results ==="
python experiments/compare_ml_hybrid_bonus.py \
  --inputs \
    bonus8=artifacts/ml_hybrid_bonus8_100g.jsonl \
    bonus10=artifacts/ml_hybrid_bonus10_100g.jsonl \
    bonus12=artifacts/ml_hybrid_bonus12_100g.jsonl \
    bonus15=artifacts/ml_hybrid_bonus15_100g.jsonl \
  --summary artifacts/ml_hybrid_bonus_sweep_summary.json

echo ""
echo "=== Done ==="
echo "Summary: artifacts/ml_hybrid_bonus_sweep_summary.json"
