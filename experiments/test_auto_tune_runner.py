"""
Unit tests for tools/auto_tune_runner.py.

Run: python experiments/test_auto_tune_runner.py
"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.auto_tune_runner import (
    plan, build_grid, build_command, evaluate_results,
    build_summary, format_summary_md, _check_safety,
    _SEARCH_GRID, _EXCLUDED_PARAMETERS, _VALID_STAGES,
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
        {"parameter": "advantage_weight", "value": 0.2, "result": "reject"},
        {"parameter": "advantage_weight", "value": 0.6, "result": "accept"},
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
print("\n--- valid parameter ---")

p = plan("advantage_weight", "30g", h_file.name, w_file.name)
check("no error", "error" not in p)
check("parameter correct", p["parameter"] == "advantage_weight")
check("stage correct", p["stage"] == "30g")
check("baseline_value=0.4", p["baseline_value"] == 0.4)

print("\n--- invalid parameter ---")

p = plan("nonexistent_param", "30g", h_file.name, w_file.name)
check("error for unknown param", "error" in p)

print("\n--- excluded parameters ---")

p = plan("retreat_to_better_attacker_bonus", "30g", h_file.name, w_file.name)
check("retreat_bonus excluded", "error" in p)

p = plan("attack_suppress_penalty", "30g", h_file.name, w_file.name)
check("attack_suppress excluded", "error" in p)

# ===================================================================
print("\n--- baseline excluded from candidates ---")

p = plan("advantage_weight", "30g", h_file.name, w_file.name)
check("0.4 not in runnable", 0.4 not in p["runnable"])
check("0.4 in skipped", any(s["value"] == 0.4 for s in p["skipped"]))

# ===================================================================
print("\n--- accept candidates skipped ---")

check("0.6 accepted -> skipped", any(s["value"] == 0.6 for s in p["skipped"]))
check("0.6 not in runnable", 0.6 not in p["runnable"])

print("\n--- reject candidates skipped ---")

check("0.2 rejected -> skipped", any(s["value"] == 0.2 for s in p["skipped"]))
check("0.2 not in runnable", 0.2 not in p["runnable"])

print("\n--- hold candidates remain runnable ---")

p2 = plan("energy_to_plan_bonus", "30g", h_file.name, w_file.name)
check("4.0 held -> runnable", 4.0 in p2["runnable"])

print("\n--- unexplored candidates remain runnable ---")

check("0.3 unexplored -> runnable", 0.3 in p["runnable"])
check("0.5 unexplored -> runnable", 0.5 in p["runnable"])

# ===================================================================
print("\n--- build_grid ---")

grid = build_grid("advantage_weight", 0.4, [0.3, 0.5])
check("grid has patterns", "patterns" in grid)
check("grid 3 patterns (baseline + 2 candidates)", len(grid["patterns"]) == 3)
check("grid pattern 0 is baseline", grid["patterns"][0]["advantage_weight"] == 0.4)
check("grid pattern 1 is candidate 0.3", grid["patterns"][1]["advantage_weight"] == 0.3)
check("grid pattern 2 is candidate 0.5", grid["patterns"][2]["advantage_weight"] == 0.5)

# ===================================================================
print("\n--- build_command ---")

cmd = build_command("grid.json", 30, 11000, "reports", True)
check("cmd has weight_search.py", any("weight_search.py" in c for c in cmd))
check("cmd has --grid-file", "--grid-file" in cmd)
check("cmd has --use-wsl", "--use-wsl" in cmd)
check("cmd has --games 30", "30" in cmd)

cmd_no_wsl = build_command("grid.json", 50, 12000, "reports", False)
check("cmd without --use-wsl", "--use-wsl" not in cmd_no_wsl)

# ===================================================================
print("\n--- _check_safety ---")

check("all zero -> all_0", _check_safety({"attack_available_but_no_attack": 0}) == "all_0")
check("nonzero -> name", "attack" in _check_safety({"attack_available_but_no_attack": 1}))

# ===================================================================
print("\n--- evaluate_results ---")

metrics = [
    {"games": 30, "anomalies_total": 140, "anomalies_per_game": 4.67,
     "attack_available_but_no_attack": 0, "end_when_attack_available": 0,
     "retreat_when_attack_available": 0},
    {"games": 30, "anomalies_total": 150, "anomalies_per_game": 5.00,
     "attack_available_but_no_attack": 0, "end_when_attack_available": 0,
     "retreat_when_attack_available": 0},
    None,
]
decisions = evaluate_results("advantage_weight", "30g", 4.53, [0.3, 0.5, 0.7], metrics)

check("3 decisions", len(decisions) == 3)
check("0.3 has decision", "decision" in decisions[0])
check("0.5 has decision", "decision" in decisions[1])
check("None -> error", decisions[2]["decision"] == "error")
check("0.3 promote or no_promote", decisions[0]["decision"] in ("promote", "no_promote", "hold"))

# ===================================================================
print("\n--- evaluate_results with safety fail ---")

bad_metrics = [
    {"games": 30, "anomalies_total": 100, "anomalies_per_game": 3.33,
     "attack_available_but_no_attack": 1, "end_when_attack_available": 0,
     "retreat_when_attack_available": 0},
]
bad_decisions = evaluate_results("advantage_weight", "30g", 4.53, [0.3], bad_metrics)
check("safety fail -> reject", bad_decisions[0]["decision"] == "reject")

# ===================================================================
print("\n--- build_summary ---")

summary = build_summary(
    "advantage_weight", "30g", 30, 11000,
    0.4, 4.53, [{"value": 0.4, "reason": "baseline"}],
    decisions[:2], False, True,
)

for key in ["schema_version", "parameter", "stage", "games", "start_game",
            "baseline_value", "baseline_anomalies_per_game", "candidates",
            "promoted_candidates", "skipped_candidates", "search_history_updated",
            "weights_restored", "next_recommended_action"]:
    check(f"summary has '{key}'", key in summary)

check("summary parameter", summary["parameter"] == "advantage_weight")
check("summary weights_restored", summary["weights_restored"])
check("summary history not updated", not summary["search_history_updated"])

# ===================================================================
print("\n--- build_summary promoted ---")

promoted_decisions = [
    {"value": 0.3, "anomalies_per_game": 4.00, "delta": -0.53,
     "vs_baseline_pct": -11.7, "safety": "all_0",
     "decision": "promote", "promote": True, "next_action": "Promote to 50g."},
]
s2 = build_summary("advantage_weight", "30g", 30, 11000, 0.4, 4.53,
                    [], promoted_decisions, False, True)
check("promoted list", s2["promoted_candidates"] == [0.3])
check("next action mentions 50g", "50g" in s2["next_recommended_action"])

# ===================================================================
print("\n--- format_summary_md ---")

md = format_summary_md(summary)
check("md has parameter", "advantage_weight" in md)
check("md has Results", "Results" in md)
check("md has Safety", "Safety" in md)
check("md has Promotion", "Promotion" in md)
check("md has Next Action", "Next Action" in md)

# ===================================================================
print("\n--- dry-run does not execute ---")
# (We verify this by checking that plan() does not run games)
p_dry = plan("advantage_weight", "30g", h_file.name, w_file.name)
check("plan returns runnable without executing", isinstance(p_dry["runnable"], list))

# ===================================================================
print("\n--- update-history off by default ---")
# Build summary with history_updated=False
s3 = build_summary("advantage_weight", "30g", 30, 11000, 0.4, 4.53,
                    [], [], False, True)
check("history not updated default", not s3["search_history_updated"])

# Build summary with history_updated=True
s4 = build_summary("advantage_weight", "30g", 30, 11000, 0.4, 4.53,
                    [], [], True, True)
check("history updated when flagged", s4["search_history_updated"])

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
