"""
Unit tests for weight_search.py baseline alignment.

Verifies that weight_search.py reads data/weights.json for baseline
values and that auto_tune.py grid output is compatible.

Run: python experiments/test_weight_search_defaults.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.weight_search import _load_baseline, _SEARCH_GRID, _WEIGHT_KEYS

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
print("\n--- baseline from data/weights.json ---")

baseline = _load_baseline()

check("baseline loaded", len(baseline) > 0)
check("advantage_weight=0.4", baseline.get("advantage_weight") == 0.4)
check("energy_to_plan_bonus=5.0", baseline.get("energy_to_plan_bonus") == 5.0)
check("energy_to_plan_bonus_no_need=2.0", baseline.get("energy_to_plan_bonus_no_need") == 2.0)
check("attack_suppress_penalty=-40.0", baseline.get("attack_suppress_penalty") == -40.0)
check("retreat_to_better_attacker_bonus=1400.0",
      baseline.get("retreat_to_better_attacker_bonus") == 1400.0)

# ===================================================================
print("\n--- weight keys coverage ---")

check("advantage_weight in WEIGHT_KEYS", "advantage_weight" in _WEIGHT_KEYS)
check("energy_to_plan_bonus in WEIGHT_KEYS", "energy_to_plan_bonus" in _WEIGHT_KEYS)
check("energy_to_plan_bonus_no_need in WEIGHT_KEYS", "energy_to_plan_bonus_no_need" in _WEIGHT_KEYS)
check("attack_suppress_penalty in WEIGHT_KEYS", "attack_suppress_penalty" in _WEIGHT_KEYS)
check("retreat_to_better_attacker_bonus in WEIGHT_KEYS",
      "retreat_to_better_attacker_bonus" in _WEIGHT_KEYS)

# ===================================================================
print("\n--- search grid matches auto_tune.py ---")

from tools.auto_tune import _SEARCH_GRID as AT_GRID

for param, values in AT_GRID.items():
    check(f"grid {param} matches auto_tune", _SEARCH_GRID.get(param) == values)

# ===================================================================
print("\n--- auto_tune grid_file compatibility ---")

from tools.auto_tune import generate_plan

weights_path = os.path.join(os.path.dirname(__file__), "..", "data", "weights.json")
history_path = os.path.join(os.path.dirname(__file__), "..", "reports", "search_history.json")
plan = generate_plan(weights_path, history_path, "30g")

grid_file = plan["grid_file"]
check("grid_file has patterns", "patterns" in grid_file)
check("grid_file patterns is list", isinstance(grid_file["patterns"], list))

if grid_file["patterns"]:
    p = grid_file["patterns"][0]
    merged = dict(baseline)
    merged.update(p)
    check("merged pattern has attack_suppress=-40",
          merged.get("attack_suppress_penalty") == -40.0)
    check("merged pattern has retreat_bonus=1400",
          merged.get("retreat_to_better_attacker_bonus") == 1400.0)

# ===================================================================
print("\n--- grid_file round-trip via temp file ---")

tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
json.dump(grid_file, tmp)
tmp.close()

with open(tmp.name, encoding="utf-8") as f:
    reloaded = json.load(f)

check("round-trip patterns count", len(reloaded["patterns"]) == len(grid_file["patterns"]))

if reloaded["patterns"]:
    p = reloaded["patterns"][0]
    merged = dict(baseline)
    merged.update(p)
    check("round-trip retains correct values",
          all(k in merged for k in _WEIGHT_KEYS))

os.unlink(tmp.name)

# ===================================================================
print("\n--- baseline excludes non-weight keys ---")

check("schema_version not in baseline", "schema_version" not in baseline)
check("description not in baseline", "description" not in baseline)
check("notes not in baseline", "notes" not in baseline)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
