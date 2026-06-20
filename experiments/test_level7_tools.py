"""
Unit tests for Level 7 tools: evaluate_candidate, prepare_pr_candidate, generate_pr_metadata.

Run: python experiments/test_level7_tools.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.evaluate_candidate import evaluate
from tools.prepare_pr_candidate import prepare
from tools.generate_pr_metadata import generate_metadata

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0

def check(label, condition):
    global _failures
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        _failures += 1

_SAFETY_ALL_ZERO = [
    {"metric": "attack_available_but_no_attack", "before": 0, "after": 0, "delta": 0},
    {"metric": "end_when_attack_available", "before": 0, "after": 0, "delta": 0},
    {"metric": "retreat_when_attack_available", "before": 0, "after": 0, "delta": 0},
    {"metric": "ability_without_followup_attack", "before": 0, "after": 0, "delta": 0},
]

_BASE_BEFORE = {"games": 50, "anomalies_total": 250, "attack_available_but_no_attack": 0,
                "end_when_attack_available": 0, "retreat_when_attack_available": 0,
                "ability_without_followup_attack": 0}

# ---------------------------------------------------------------------------
# evaluate_candidate
# ---------------------------------------------------------------------------
print("\n--- evaluate_candidate ---")

r = evaluate(_BASE_BEFORE,
             {**_BASE_BEFORE, "anomalies_total": 200},
             "good_candidate", 20)
check("clear improvement -> accept", r["decision"] == "accept")

r = evaluate(_BASE_BEFORE,
             {**_BASE_BEFORE, "anomalies_total": 300},
             "worse_candidate", 20)
check("anomalies worsened -> reject", r["decision"] == "reject")

r = evaluate(_BASE_BEFORE,
             {**_BASE_BEFORE, "attack_available_but_no_attack": 1},
             "safety_nonzero", 20)
check("safety after>0 -> reject", r["decision"] == "reject")
check("reject reason mentions 'not zero'", "not zero" in r["reasons"][0].lower() or "not zero" in r.get("next_action","").lower())

r = evaluate(_BASE_BEFORE, {**_BASE_BEFORE}, "same", 20)
check("no change -> hold", r["decision"] == "hold")

r = evaluate({"games": 5}, {"games": 5}, "few_games", 20)
check("insufficient games -> hold", r["decision"] == "hold")

# ---------------------------------------------------------------------------
# prepare_pr_candidate
# ---------------------------------------------------------------------------
print("\n--- prepare_pr_candidate ---")

r = prepare({"candidate": "test", "decision": "accept", "games_before": 50, "games_after": 50,
             "improved_metrics": [], "worsened_metrics": [], "safe_metrics": list(_SAFETY_ALL_ZERO),
             "missing_metrics": [], "reasons": [], "next_action": "",
             "suggested_changed_files": ["data/weights.json"]})
check("accept + safety OK -> eligible", r["eligible_for_pr"])

r = prepare({"candidate": "test", "decision": "reject", "reasons": [], "next_action": ""})
check("reject -> not eligible", not r["eligible_for_pr"])

r = prepare({"candidate": "test", "decision": "accept", "games_before": 50, "games_after": 50,
             "improved_metrics": [], "worsened_metrics": [], "safe_metrics": [],
             "missing_metrics": ["attack_available_but_no_attack"], "reasons": [], "next_action": "",
             "suggested_changed_files": []})
check("safety missing -> not eligible", not r["eligible_for_pr"])

# ---------------------------------------------------------------------------
# generate_pr_metadata
# ---------------------------------------------------------------------------
print("\n--- generate_pr_metadata ---")

r = generate_metadata({"eligible_for_pr": False, "candidate": "x", "reason": "no"})
check("not eligible -> not ready", not r["ready_to_create_pr"])

r = generate_metadata({"eligible_for_pr": True, "candidate": "test",
                        "improved_metrics": [], "worsened_metrics": [],
                        "safe_metrics": _SAFETY_ALL_ZERO[:3],
                        "missing_metrics": [], "reasons": [], "next_action": "",
                        "suggested_changed_files": [], "games_before": 50, "games_after": 50})
check("safety 1 missing -> not ready", not r["ready_to_create_pr"])

r = generate_metadata({"eligible_for_pr": True, "candidate": "test",
                        "improved_metrics": [], "worsened_metrics": [],
                        "safe_metrics": list(_SAFETY_ALL_ZERO),
                        "missing_metrics": [], "reasons": [], "next_action": "",
                        "suggested_changed_files": [], "games_before": 50, "games_after": 50})
check("all 4 safety zero -> ready", r["ready_to_create_pr"])

r = generate_metadata({"eligible_for_pr": True, "candidate": "test",
                        "improved_metrics": [], "worsened_metrics": [],
                        "safe_metrics": [
                            {"metric": "attack_available_but_no_attack", "before": 0, "after": 2, "delta": 2},
                            {"metric": "end_when_attack_available", "before": 0, "after": 0, "delta": 0},
                            {"metric": "retreat_when_attack_available", "before": 0, "after": 0, "delta": 0},
                            {"metric": "ability_without_followup_attack", "before": 0, "after": 0, "delta": 0},
                        ],
                        "missing_metrics": [], "reasons": [], "next_action": "",
                        "suggested_changed_files": [], "games_before": 50, "games_after": 50})
check("safety after>0 -> not ready", not r["ready_to_create_pr"])

r = generate_metadata({"eligible_for_pr": True, "candidate": "retreat_bonus=1400",
                        "improved_metrics": [], "worsened_metrics": [],
                        "safe_metrics": list(_SAFETY_ALL_ZERO),
                        "missing_metrics": [], "reasons": [], "next_action": "Adopt.",
                        "suggested_changed_files": ["data/weights.json"], "games_before": 200, "games_after": 200})
check("title generated", r.get("title", "").startswith("feat:"))
check("branch has timestamp", len(r.get("branch_name", "")) > 30)
check("branch starts with feat/", r.get("branch_name", "").startswith("feat/"))
check("files in output", "data/weights.json" in r.get("suggested_changed_files", []))

# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
total = 18
print(f"  Passed: {total - _failures}/{total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
