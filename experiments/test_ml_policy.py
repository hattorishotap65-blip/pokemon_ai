"""
Tests for agent/ml_policy.py and agent/policy_router.py.

Run: python experiments/test_ml_policy.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0
_total = 0

def check(label, condition):
    global _failures, _total
    _total += 1
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        _failures += 1

# ===================================================================
print("\n--- policy_router ---")

from agent.policy_router import get_policy_mode, should_use_ml_policy, should_use_hybrid_policy

mode = get_policy_mode()
check("Default mode is rule_based", mode == "rule_based")
check("should_use_ml default False", not should_use_ml_policy())
check("should_use_hybrid default False", not should_use_hybrid_policy())

# Test with env var
os.environ["POKEMON_AI_POLICY_MODE"] = "hybrid"
check("Hybrid mode", get_policy_mode() == "hybrid")
check("Hybrid: should_use_hybrid", should_use_hybrid_policy())
check("Hybrid: not should_use_ml", not should_use_ml_policy())

os.environ["POKEMON_AI_POLICY_MODE"] = "ml"
check("ML mode", get_policy_mode() == "ml")
check("ML: should_use_ml", should_use_ml_policy())
check("ML: should_use_hybrid also True", should_use_hybrid_policy())

os.environ["POKEMON_AI_POLICY_MODE"] = "invalid"
check("Invalid mode falls back to rule_based", get_policy_mode() == "rule_based")

# Restore
os.environ.pop("POKEMON_AI_POLICY_MODE", None)
check("Restored default", get_policy_mode() == "rule_based")

# ===================================================================
print("\n--- ml_policy scoring ---")

import agent.ml_policy as ml_policy
ml_policy._LOADED = False
ml_policy._ENABLED = False
ml_policy._WEIGHTS = {}

from agent.ml_policy import score_ml_policy, is_ml_policy_enabled

check("ML policy disabled by default", not is_ml_policy_enabled())

score, reason = score_ml_policy({"type": 13}, {"active_pokemon": {}})
check("Disabled: score=0", score == 0.0)
check("Disabled: reason empty", reason == "")

# Force enable with empty weights
ml_policy._LOADED = True
ml_policy._ENABLED = True
ml_policy._WEIGHTS = {}

score2, reason2 = score_ml_policy({"type": 13}, {"active_pokemon": {}})
check("Enabled empty weights: score=0", score2 == 0.0)
check("Enabled empty weights: reason=ml_no_weights", reason2 == "ml_no_weights")

# Force enable with simple weight
ml_policy._WEIGHTS = {"is_attack": 5.0}
score3, reason3 = score_ml_policy({"type": 13, "attackId": 1}, {"active_pokemon": {}})
check("Enabled with is_attack weight: score=5", score3 == 5.0)
check("Enabled: reason=ml_linear", reason3 == "ml_linear")

# Non-attack should get 0 for is_attack weight
score4, _ = score_ml_policy({"type": 14}, {"active_pokemon": {}})
check("End action: is_attack=False -> score=0", score4 == 0.0)

# Reset
ml_policy._LOADED = False
ml_policy._ENABLED = False
ml_policy._WEIGHTS = {}

# ===================================================================
print("\n--- ml_policy error handling ---")

ml_policy._LOADED = True
ml_policy._ENABLED = True
ml_policy._WEIGHTS = {"nonexistent_feature": 10.0}

score5, reason5 = score_ml_policy({"type": 13}, {})
check("Unknown feature: no crash", isinstance(score5, float))

ml_policy._LOADED = False
ml_policy._ENABLED = False
ml_policy._WEIGHTS = {}

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
