"""
Unit tests for tools/promotion_gate.py.

Run: python experiments/test_promotion_gate.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.promotion_gate import evaluate_stage

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
# 30g stage
# ===================================================================
print("\n--- 30g: promote ---")

r = evaluate_stage("30g", 4.97, 4.40, "all_0")
check("30g improved -> promote", r["promote"])
check("30g decision=promote", r["decision"] == "promote")
check("30g delta negative", r["delta"] < 0)
check("30g safety_ok", r["safety_ok"])

print("\n--- 30g: worse ---")

r = evaluate_stage("30g", 4.97, 5.17, "all_0")
check("30g worse -> no promote", not r["promote"])
check("30g decision=no_promote", r["decision"] == "no_promote")

print("\n--- 30g: no change ---")

r = evaluate_stage("30g", 4.97, 4.97, "all_0")
check("30g no change -> no promote", not r["promote"])

print("\n--- 30g: safety fail ---")

r = evaluate_stage("30g", 4.97, 4.40, "retreat_when_attack_available=1")
check("30g safety fail -> reject", r["decision"] == "reject")
check("30g safety fail -> no promote", not r["promote"])
check("30g safety_ok=false", not r["safety_ok"])

print("\n--- 30g: category regression ---")

r = evaluate_stage("30g", 4.97, 4.40, "all_0",
                   category_regressions=[{"category": "bb_correct", "delta_pct": 25}])
check("30g cat regression -> hold", r["decision"] == "hold")
check("30g cat regression -> no promote", not r["promote"])

print("\n--- 30g: small category regression (below threshold) ---")

r = evaluate_stage("30g", 4.97, 4.40, "all_0",
                   category_regressions=[{"category": "bb_correct", "delta_pct": 10}])
check("30g small cat regression -> promote", r["promote"])

# ===================================================================
# 50g stage
# ===================================================================
print("\n--- 50g: promote ---")

r = evaluate_stage("50g", 4.94, 4.38, "all_0")
check("50g improved -> promote", r["promote"])
check("50g decision=promote", r["decision"] == "promote")
check("50g next_action mentions 200g", "200g" in r["next_action"])

print("\n--- 50g: improvement lost ---")

r = evaluate_stage("50g", 4.94, 5.10, "all_0")
check("50g worse -> no promote", not r["promote"])
check("50g decision=no_promote", r["decision"] == "no_promote")

print("\n--- 50g: safety fail ---")

r = evaluate_stage("50g", 4.94, 4.38, "end_when_attack_available=2")
check("50g safety fail -> reject", r["decision"] == "reject")

# ===================================================================
# 200g stage: accept
# ===================================================================
print("\n--- 200g: accept ---")

r = evaluate_stage("200g", 4.97, 4.50, "all_0",
                   consistency={"30g": -11, "50g": -11, "200g": -9.5})
check("200g accept", r["decision"] == "accept")
check("200g no promote (final)", not r["promote"])
check("200g improvement negative", r["improvement_percent"] < 0)
check("200g next_action=adoption PR", "adoption" in r["next_action"].lower() or "pr" in r["next_action"].lower())

# ===================================================================
# 200g stage: hold (marginal)
# ===================================================================
print("\n--- 200g: hold marginal ---")

r = evaluate_stage("200g", 4.97, 4.90, "all_0")
check("200g marginal -> hold", r["decision"] == "hold")
check("200g marginal reason", "marginal" in r["reason"].lower())

# ===================================================================
# 200g stage: hold (category regression)
# ===================================================================
print("\n--- 200g: hold category regression ---")

r = evaluate_stage("200g", 4.97, 4.40, "all_0",
                   category_regressions=[{"category": "kw_f0007", "delta_pct": 30}])
check("200g cat regression -> hold", r["decision"] == "hold")
check("200g cat regression in reason", "regression" in r["reason"].lower())

# ===================================================================
# 200g stage: hold (inconsistent)
# ===================================================================
print("\n--- 200g: hold inconsistent ---")

r = evaluate_stage("200g", 4.97, 4.50, "all_0",
                   consistency={"30g": -11, "50g": 3, "200g": -9.5})
check("200g inconsistent -> hold", r["decision"] == "hold")
check("200g inconsistent reason", "inconsistent" in r["reason"].lower())

# ===================================================================
# 200g stage: reject (worse)
# ===================================================================
print("\n--- 200g: reject worse ---")

r = evaluate_stage("200g", 4.97, 5.20, "all_0")
check("200g worse -> reject", r["decision"] == "reject")

# ===================================================================
# 200g stage: reject (safety)
# ===================================================================
print("\n--- 200g: reject safety ---")

r = evaluate_stage("200g", 4.97, 4.40, "attack_available_but_no_attack=1")
check("200g safety fail -> reject", r["decision"] == "reject")

# ===================================================================
# 200g stage: no change
# ===================================================================
print("\n--- 200g: hold no change ---")

r = evaluate_stage("200g", 4.97, 4.97, "all_0")
check("200g no change -> hold", r["decision"] == "hold")

# ===================================================================
# Output fields
# ===================================================================
print("\n--- output fields ---")

r = evaluate_stage("30g", 4.97, 4.40, "all_0")
check("has stage", "stage" in r)
check("has decision", "decision" in r)
check("has promote", "promote" in r)
check("has reason", "reason" in r)
check("has baseline_apg", "baseline_anomalies_per_game" in r)
check("has candidate_apg", "candidate_anomalies_per_game" in r)
check("has delta", "delta" in r)
check("has improvement_percent", "improvement_percent" in r)
check("has safety_ok", "safety_ok" in r)
check("has category_regressions", "category_regressions" in r)
check("has next_action", "next_action" in r)
check("has date", "date" in r)

# ===================================================================
# Unknown stage
# ===================================================================
print("\n--- unknown stage ---")

r = evaluate_stage("999g", 4.97, 4.40, "all_0")
check("unknown stage -> error", r["decision"] == "error")
check("unknown stage -> no promote", not r["promote"])

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
