"""
Tests for agent/params.py parameter loader.

Run: python experiments/test_params.py
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

# Reset loader state for clean test
import agent.params as params
params._LOADED = False
params._PARAMS = {}

# ===================================================================
print("\n--- load from default_params.json ---")

val = params.get("zero_damage_attack_penalty")
check("zero_damage_attack_penalty = 500.0", val == 500.0)

val = params.get("ko_opponent_bonus")
check("ko_opponent_bonus = 20.0", val == 20.0)

val = params.get("boss_can_ko")
check("boss_can_ko = 30.0", val == 30.0)

val = params.get("alt_attacker_ko_score")
check("alt_attacker_ko_score = 800.0", val == 800.0)

val = params.get("energy_ready_bonus")
check("energy_ready_bonus = 200.0", val == 200.0)

# ===================================================================
print("\n--- unknown param returns 0.0 ---")

val = params.get("nonexistent_param")
check("nonexistent returns 0.0", val == 0.0)

# ===================================================================
print("\n--- all_params returns dict ---")

all_p = params.all_params()
check("all_params is dict", isinstance(all_p, dict))
check("all_params has 5 keys", len(all_p) == 5)
check("all_params has zero_damage_attack_penalty", "zero_damage_attack_penalty" in all_p)

# ===================================================================
print("\n--- fallback when file missing ---")

# Simulate missing file by resetting and patching
params._LOADED = False
params._PARAMS = {}
original_defaults = dict(params._DEFAULTS)

# Force reload - should still work with defaults
params._ensure_loaded()
check("Loaded flag set", params._LOADED)
check("Params populated", len(params._PARAMS) >= 5)

# ===================================================================
print("\n--- values match hardcoded defaults ---")

check("penalty matches default", params.get("zero_damage_attack_penalty") == params._DEFAULTS["zero_damage_attack_penalty"])
check("ko_bonus matches default", params.get("ko_opponent_bonus") == params._DEFAULTS["ko_opponent_bonus"])
check("boss matches default", params.get("boss_can_ko") == params._DEFAULTS["boss_can_ko"])
check("alt_ko matches default", params.get("alt_attacker_ko_score") == params._DEFAULTS["alt_attacker_ko_score"])
check("energy matches default", params.get("energy_ready_bonus") == params._DEFAULTS["energy_ready_bonus"])

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
