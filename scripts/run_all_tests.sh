#!/bin/bash
# Run all test suites. Exit 1 on first failure.
set -e

echo "=== Level 7 tools ==="
python experiments/test_level7_tools.py

echo ""
echo "=== Effect engine ==="
python experiments/test_effect_engine.py

echo ""
echo "=== Turn rule engine ==="
python experiments/test_turn_rule_engine.py

echo ""
echo "=== Voltorb attack ==="
python experiments/test_voltorb_attack.py

echo ""
echo "=== Kilowattrel ability ==="
python experiments/test_kilowattrel_ability.py

echo ""
echo "=== Search history ==="
python experiments/test_search_history.py

echo ""
echo "=== Promotion gate ==="
python experiments/test_promotion_gate.py

echo ""
echo "=== Auto tune ==="
python experiments/test_auto_tune.py

echo ""
echo "=== Weight search defaults ==="
python experiments/test_weight_search_defaults.py

echo ""
echo "=== Auto tune runner ==="
python experiments/test_auto_tune_runner.py

echo ""
echo "=== Bench liability ==="
python experiments/test_bench_liability.py

echo ""
echo "=== Card metadata ==="
python experiments/test_card_metadata.py

echo ""
echo "All tests passed."
