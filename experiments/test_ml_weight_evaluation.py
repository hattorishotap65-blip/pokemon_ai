"""
Tests for experiments/evaluate_ml_weights.py.

Run: python experiments/test_ml_weight_evaluation.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.evaluate_ml_weights import (
    parse_match_output, make_eval_env, prepare_eval_weights,
    cleanup_eval_weights, compute_verdict, save_result,
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
print("\n--- parse_match_output ---")

SAMPLE_OUTPUT = """
Game 30/30: g85029  W=7 L=8 D=15   score=222
  Timeouts       :    0  (  0.0%)
  Errors         :    0  (  0.0%)
  Avg selections : 189.3
  Elapsed        : 95.1s  (3168ms/game)
  Results CSV    : logs/real_20260623.csv
"""
parsed = parse_match_output(SAMPLE_OUTPUT)
check("Parse errors=0", parsed["errors"] == 0)
check("Parse timeouts=0", parsed["timeouts"] == 0)
check("Parse avg_selections", parsed["avg_selections"] == 189.3)
check("Parse avg_ms", parsed["avg_ms"] == 3168)

SAMPLE_ERR = """
  Errors         :    2  (  6.7%)
  Timeouts       :    1  (  3.3%)
  Avg selections : 150.0
  Elapsed        : 60.0s  (2000ms/game)
"""
parsed_err = parse_match_output(SAMPLE_ERR)
check("Parse errors=2", parsed_err["errors"] == 2)
check("Parse timeouts=1", parsed_err["timeouts"] == 1)

parsed_empty = parse_match_output("")
check("Empty stdout: no crash", isinstance(parsed_empty, dict))

# ===================================================================
print("\n--- make_eval_env ---")

env_bl = make_eval_env("rule_based")
check("Baseline mode", env_bl["POKEMON_AI_POLICY_MODE"] == "rule_based")
check("No weights path in baseline", "POKEMON_AI_ML_WEIGHTS_PATH" not in env_bl)

env_hy = make_eval_env("hybrid", "/tmp/w.json")
check("Hybrid mode", env_hy["POKEMON_AI_POLICY_MODE"] == "hybrid")
check("Weights path set", env_hy["POKEMON_AI_ML_WEIGHTS_PATH"] == os.path.abspath("/tmp/w.json"))

# ===================================================================
print("\n--- prepare_eval_weights ---")

with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, "src.json")
    dst = os.path.join(td, "sub", "dst.json")
    with open(src, "w") as f:
        json.dump({"enabled": False, "weights": {"a": 1.0}}, f)

    ok = prepare_eval_weights(src, dst)
    check("Prepare succeeds", ok)
    check("Eval file exists", os.path.exists(dst))

    with open(dst) as f:
        data = json.load(f)
    check("Eval enabled=True", data["enabled"] == True)
    check("Weights preserved", data["weights"]["a"] == 1.0)

    # Source unchanged
    with open(src) as f:
        src_data = json.load(f)
    check("Source enabled=False", src_data["enabled"] == False)

    cleanup_eval_weights(dst)
    check("Cleanup removes file", not os.path.exists(dst))

# ===================================================================
print("\n--- prepare from nonexistent ---")

ok2 = prepare_eval_weights("/nonexistent/path.json", "/tmp/out.json")
check("Nonexistent source: returns False", not ok2)

# ===================================================================
print("\n--- compute_verdict ---")

bl = {"errors": 0, "timeouts": 0, "avg_selections": 190}
cd = {"errors": 0, "timeouts": 0, "avg_selections": 195}
v = compute_verdict(bl, cd)
check("Verdict ok", v["verdict"] == "candidate_ok")
check("Delta selections", v["delta"]["avg_selections_diff"] == 5.0)

cd_err = {"errors": 1, "timeouts": 0, "avg_selections": 190}
v_err = compute_verdict(bl, cd_err)
check("Candidate errors -> unsafe", v_err["verdict"] == "candidate_unsafe")

cd_to = {"errors": 0, "timeouts": 2, "avg_selections": 190}
v_to = compute_verdict(bl, cd_to)
check("Candidate timeouts -> unsafe", v_to["verdict"] == "candidate_unsafe")

# ===================================================================
print("\n--- save_result ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "result.json")
    r = save_result(path, "w.json", "hybrid", bl, cd, v)
    check("Result file exists", os.path.exists(path))

    with open(path) as f:
        loaded = json.load(f)
    check("Valid JSON", isinstance(loaded, dict))
    check("Has weights_path", loaded["weights_path"] == "w.json")
    check("Has mode", loaded["mode"] == "hybrid")
    check("Has baseline", "baseline" in loaded)
    check("Has candidate", "candidate" in loaded)
    check("Has verdict", loaded["verdict"] == "candidate_ok")

# ===================================================================
print("\n--- configs not modified ---")

cfg_path = os.path.join(os.path.dirname(__file__), "..", "configs", "ml_policy_weights.json")
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        cfg = json.load(f)
    check("configs enabled=false", cfg["enabled"] == False)
    check("configs weights empty", cfg["weights"] == {})
else:
    check("configs exists", False)

# ===================================================================
print("\n--- env var in ml_policy ---")

import agent.ml_policy as ml_policy
ml_policy._LOADED = False
ml_policy._ENABLED = False
ml_policy._WEIGHTS = {}

with tempfile.TemporaryDirectory() as td:
    wp = os.path.join(td, "test_w.json")
    with open(wp, "w") as f:
        json.dump({"enabled": True, "weights": {"is_attack": 2.0}}, f)
    os.environ["POKEMON_AI_ML_WEIGHTS_PATH"] = wp
    ml_policy._LOADED = False
    ml_policy._ensure_loaded()
    check("Env var loads weights", ml_policy._ENABLED == True)
    check("Env var weights loaded", ml_policy._WEIGHTS.get("is_attack") == 2.0)

os.environ.pop("POKEMON_AI_ML_WEIGHTS_PATH", None)
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
