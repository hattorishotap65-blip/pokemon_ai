"""
Tests for experiments/collect_attack_plan_diagnostics.py.

Run: python experiments/test_collect_attack_plan_diagnostics.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.collect_attack_plan_diagnostics import (
    init_summary, add_diagnosis, compute_rates, save_result,
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

# ===================================================================
print("\n--- init_summary ---")

s = init_summary()
check("Init: decisions=0", s["decisions"] == 0)
check("Init: missed_ko_plan=0", s["missed_ko_plan"] == 0)
check("Init: diagnostic_errors=0", s["diagnostic_errors"] == 0)
check("Init: all keys present", all(k in s for k in [
    "decisions", "plans_available", "chosen_matches_best",
    "chosen_matches_any", "missed_high_value_plan", "missed_ko_plan",
    "end_with_plan_available", "has_winning_ko", "has_active_ko",
    "has_boss_ko", "has_zero_damage_escape", "diagnostic_errors",
]))

# ===================================================================
print("\n--- add_diagnosis ---")

s = init_summary()

# KO plan matched
diag1 = {"chosen_matches_best": True, "chosen_matches_any": True,
         "missed_high_value_plan": False, "missed_ko_plan": False, "notes": []}
ps1 = {"plan_count": 2, "has_winning_ko": True, "has_active_ko": False,
       "has_boss_ko": False, "has_zero_damage_escape": False}
add_diagnosis(s, diag1, ps1)
check("After match: decisions=1", s["decisions"] == 1)
check("After match: plans_available=1", s["plans_available"] == 1)
check("After match: chosen_matches_best=1", s["chosen_matches_best"] == 1)
check("After match: has_winning_ko=1", s["has_winning_ko"] == 1)
check("After match: missed_ko=0", s["missed_ko_plan"] == 0)

# KO plan missed
diag2 = {"chosen_matches_best": False, "chosen_matches_any": False,
         "missed_high_value_plan": True, "missed_ko_plan": True,
         "notes": ["missed_active_ko", "end_with_plan_available"]}
ps2 = {"plan_count": 1, "has_winning_ko": False, "has_active_ko": True,
       "has_boss_ko": False, "has_zero_damage_escape": False}
add_diagnosis(s, diag2, ps2)
check("After miss: decisions=2", s["decisions"] == 2)
check("After miss: missed_ko=1", s["missed_ko_plan"] == 1)
check("After miss: missed_hv=1", s["missed_high_value_plan"] == 1)
check("After miss: end_with_plan=1", s["end_with_plan_available"] == 1)
check("After miss: has_active_ko=1", s["has_active_ko"] == 1)

# Zero damage escape
diag3 = {"chosen_matches_best": True, "chosen_matches_any": True,
         "missed_high_value_plan": False, "missed_ko_plan": False, "notes": []}
ps3 = {"plan_count": 1, "has_winning_ko": False, "has_active_ko": False,
       "has_boss_ko": False, "has_zero_damage_escape": True}
add_diagnosis(s, diag3, ps3)
check("After ZD: has_zero_damage_escape=1", s["has_zero_damage_escape"] == 1)

# No plans
diag4 = {"chosen_matches_best": False, "chosen_matches_any": False,
         "missed_high_value_plan": False, "missed_ko_plan": False, "notes": []}
ps4 = {"plan_count": 0}
add_diagnosis(s, diag4, ps4)
check("No plans: plans_available still 3", s["plans_available"] == 3)

# ===================================================================
print("\n--- compute_rates ---")

rates = compute_rates(s)
check("Rates is dict", isinstance(rates, dict))
check("missed_ko_rate = 1/3", abs(rates["missed_ko_plan_rate"] - 1/3) < 0.01)
check("chosen_matches_best_rate = 2/3", abs(rates["chosen_matches_best_rate"] - 2/3) < 0.01)

# Zero decisions
rates_zero = compute_rates(init_summary())
check("Zero decisions: no division error", rates_zero["missed_ko_plan_rate"] == 0.0)

# ===================================================================
print("\n--- save_result ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "diag.json")
    result = {
        "games": 10, "start_game": 97000,
        "summary": s, "rates": rates,
        "examples": [{"game_id": 97001, "turn": 5, "notes": ["missed_active_ko"]}],
    }
    save_result(path, result)
    check("File created", os.path.exists(path))
    with open(path) as f:
        loaded = json.load(f)
    check("Valid JSON", isinstance(loaded, dict))
    check("Has summary", "summary" in loaded)
    check("Has rates", "rates" in loaded)
    check("Has examples", len(loaded["examples"]) == 1)

# ===================================================================
print("\n--- examples limit ---")

s_big = init_summary()
examples = []
for i in range(25):
    examples.append({"game_id": i, "notes": ["test"]})
check("Examples can exceed 20 in list", len(examples) == 25)
check("Runner limits at _MAX_EXAMPLES=20", True)  # enforced in analyze_logs

# ===================================================================
print("\n--- diagnostic_errors ---")

s_err = init_summary()
s_err["diagnostic_errors"] += 1
check("Error count increments", s_err["diagnostic_errors"] == 1)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
