"""
Tests for agent/ml_features.py.

Run: python experiments/test_ml_features.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.ml_features import (
    extract_state_features, extract_action_features,
    extract_damage_features, extract_plan_features, extract_features,
)

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

STATE = {
    "active_pokemon": {"card_id": "269", "hp_remaining": 250, "energy_count": 4,
                       "is_ex": True, "attacks": [{"damage": 230}], "abilities": []},
    "bench": [{"card_id": "265", "hp_remaining": 70}],
    "prizes_remaining": 3, "turn": 5, "deck_count": 20, "hand_count": 4,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "999", "hp_remaining": 100, "is_ex": False,
                           "abilities": [], "attacks": []},
        "bench": [{"card_id": "888"}],
    },
}

ACTION_ATK = {"type": 13, "attackId": 1}
ACTION_END = {"type": 14}

# ===================================================================
print("\n--- state features ---")

sf = extract_state_features(STATE)
check("State features is dict", isinstance(sf, dict))
check("prizes_remaining", sf["prizes_remaining"] == 3)
check("opp_prizes", sf["opponent_prizes_remaining"] == 4)
check("my_active_hp", sf["my_active_hp"] == 250)
check("my_active_is_ex", sf["my_active_is_ex"] == True)
check("bench_count", sf["bench_count"] == 1)
check("opp_bench_count", sf["opp_bench_count"] == 1)
check("deck_count", sf["deck_count"] == 20)
check("turn", sf["turn"] == 5)

sf_empty = extract_state_features({})
check("Empty state: no crash", isinstance(sf_empty, dict))
sf_none = extract_state_features(None)
check("None state: no crash", isinstance(sf_none, dict))

# ===================================================================
print("\n--- action features ---")

af = extract_action_features(ACTION_ATK, STATE)
check("Action features is dict", isinstance(af, dict))
check("is_attack", af["is_attack"] == True)
check("is_end", af["is_end"] == False)
check("action_type", af["action_type"] == 13)

af_end = extract_action_features(ACTION_END, STATE)
check("End: is_end", af_end["is_end"] == True)
check("End: is_attack", af_end["is_attack"] == False)

af_none = extract_action_features(None, STATE)
check("None action: no crash", isinstance(af_none, dict))

# ===================================================================
print("\n--- damage features ---")

df = extract_damage_features(ACTION_ATK, STATE)
check("Damage features is dict", isinstance(df, dict))
check("Has predicted_damage", "predicted_damage" in df)
check("Has can_ko", "can_ko" in df)

df_empty = extract_damage_features({}, {})
check("Empty: no crash", isinstance(df_empty, dict))

# ===================================================================
print("\n--- plan features ---")

pf = extract_plan_features(STATE, ACTION_ATK)
check("Plan features is dict", isinstance(pf, dict))
check("Has best_plan_type", "best_plan_type" in pf)
check("Has action_matches_plan", "action_matches_plan" in pf)
check("Has top_plan_count", "top_plan_count" in pf)

pf_empty = extract_plan_features({}, {})
check("Empty: no crash", isinstance(pf_empty, dict))

# ===================================================================
print("\n--- combined features ---")

cf = extract_features(STATE, ACTION_ATK)
check("Combined is dict", isinstance(cf, dict))
check("Has state keys", "prizes_remaining" in cf)
check("Has action keys", "is_attack" in cf)
check("Has plan keys", "best_plan_type" in cf)

cf_none = extract_features(None, None)
check("None inputs: no crash", isinstance(cf_none, dict))

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
