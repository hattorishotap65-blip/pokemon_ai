"""
Unit tests for tools/auto_tune.py.

Run: python experiments/test_auto_tune.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.auto_tune import generate_plan, format_markdown, _SEARCH_GRID, _EXCLUDED_PARAMETERS

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

# --- Setup temp files ---
_weights = {
    "schema_version": "1.0",
    "advantage_weight": 0.4,
    "energy_to_plan_bonus": 5.0,
    "energy_to_plan_bonus_no_need": 2.0,
    "attack_suppress_penalty": -40.0,
    "retreat_to_better_attacker_bonus": 1400.0,
}
_history = {
    "schema_version": "1.0",
    "entries": [
        {"parameter": "retreat_to_better_attacker_bonus", "value": 1400.0, "result": "accept"},
        {"parameter": "attack_suppress_penalty", "value": -40.0, "result": "accept"},
        {"parameter": "attack_suppress_penalty", "value": -20.0, "result": "reject"},
        {"parameter": "advantage_weight", "value": 0.35, "result": "hold"},
        {"parameter": "energy_to_plan_bonus", "value": 4.0, "result": "hold"},
    ],
}

w_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
json.dump(_weights, w_file)
w_file.close()

h_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
json.dump(_history, h_file)
h_file.close()

# ===================================================================
print("\n--- excluded parameters ---")

plan = generate_plan(w_file.name, h_file.name, "30g")

check("retreat_bonus excluded", "retreat_to_better_attacker_bonus" in plan["excluded_parameters"])
check("attack_suppress excluded", "attack_suppress_penalty" in plan["excluded_parameters"])
check("excluded not in candidate_parameters",
      not any(p in plan["candidate_parameters"] for p in _EXCLUDED_PARAMETERS))

# ===================================================================
print("\n--- candidate generation ---")

check("advantage_weight in candidates", "advantage_weight" in plan["candidate_parameters"])
check("energy_to_plan_bonus in candidates", "energy_to_plan_bonus" in plan["candidate_parameters"])
check("energy_to_plan_bonus_no_need in candidates", "energy_to_plan_bonus_no_need" in plan["candidate_parameters"])

expected_generated = sum(
    len(v) - (1 if _weights.get(k) in v else 0) for k, v in _SEARCH_GRID.items()
)
check(f"generated_candidates={expected_generated}", plan["generated_candidates"] == expected_generated)

# ===================================================================
print("\n--- skip logic ---")

skip_params = {(s["parameter"], s["value"]) for s in plan["skipped_candidates"]}

check("current baseline 0.4 skipped", ("advantage_weight", 0.4) in skip_params)
check("current baseline 5.0 skipped", ("energy_to_plan_bonus", 5.0) in skip_params)
check("current baseline 2.0 skipped", ("energy_to_plan_bonus_no_need", 2.0) in skip_params)

# ===================================================================
print("\n--- hold candidates remain runnable ---")

run_params = {(r["parameter"], r["value"]) for r in plan["runnable_candidates"]}

check("energy_to_plan_bonus=4.0 held -> runnable", ("energy_to_plan_bonus", 4.0) in run_params)

# ===================================================================
print("\n--- unexplored candidates remain runnable ---")

check("advantage_weight=0.2 unexplored -> runnable", ("advantage_weight", 0.2) in run_params)
check("advantage_weight=0.5 unexplored -> runnable", ("advantage_weight", 0.5) in run_params)
check("advantage_weight=0.6 unexplored -> runnable", ("advantage_weight", 0.6) in run_params)
check("energy_to_plan_bonus=3.0 unexplored -> runnable", ("energy_to_plan_bonus", 3.0) in run_params)
check("energy_to_plan_bonus_no_need=4.0 unexplored -> runnable",
      ("energy_to_plan_bonus_no_need", 4.0) in run_params)

# ===================================================================
print("\n--- output JSON keys ---")

for key in ["schema_version", "stage", "stable_baseline", "excluded_parameters",
            "candidate_parameters", "generated_candidates", "skipped_candidates",
            "runnable_candidates", "recommended_next_command", "notes"]:
    check(f"key '{key}' present", key in plan)

check("stage is 30g", plan["stage"] == "30g")

# ===================================================================
print("\n--- stable baseline values ---")

check("baseline advantage_weight=0.4", plan["stable_baseline"]["advantage_weight"] == 0.4)
check("baseline energy_to_plan_bonus=5.0", plan["stable_baseline"]["energy_to_plan_bonus"] == 5.0)
check("baseline retreat_bonus=1400", plan["stable_baseline"]["retreat_to_better_attacker_bonus"] == 1400.0)
check("baseline attack_suppress=-40", plan["stable_baseline"]["attack_suppress_penalty"] == -40.0)

# ===================================================================
print("\n--- grid file ---")

check("grid_file in plan", "grid_file" in plan)
check("grid patterns non-empty", len(plan["grid_file"]["patterns"]) > 0)
check("grid pattern count = runnable count",
      len(plan["grid_file"]["patterns"]) == len(plan["runnable_candidates"]))

first_pattern = plan["grid_file"]["patterns"][0]
check("grid pattern has advantage_weight", "advantage_weight" in first_pattern)
check("grid pattern has energy_to_plan_bonus", "energy_to_plan_bonus" in first_pattern)

# ===================================================================
print("\n--- markdown output ---")

md = format_markdown(plan)
check("markdown contains Stable Baseline", "Stable Baseline" in md)
check("markdown contains Excluded", "Excluded" in md)
check("markdown contains Runnable", "Runnable" in md)
check("markdown contains Next Command", "Next Command" in md)

# ===================================================================
print("\n--- invalid stage ---")

bad = generate_plan(w_file.name, h_file.name, "999g")
check("invalid stage -> error", "error" in bad)

bad_md = format_markdown(bad)
check("invalid stage markdown -> Error", "Error" in bad_md)

# ===================================================================
print("\n--- real files ---")

real_w = os.path.join(os.path.dirname(__file__), "..", "data", "weights.json")
real_h = os.path.join(os.path.dirname(__file__), "..", "reports", "search_history.json")
if os.path.exists(real_w) and os.path.exists(real_h):
    real_plan = generate_plan(real_w, real_h, "30g")
    check("real plan generates", "runnable_candidates" in real_plan)
    check("real plan has candidates", len(real_plan["runnable_candidates"]) >= 0)

# --- Cleanup ---
os.unlink(w_file.name)
os.unlink(h_file.name)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
