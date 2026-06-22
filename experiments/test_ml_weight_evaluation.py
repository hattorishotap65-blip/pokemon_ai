"""
Tests for experiments/evaluate_ml_weights.py.

Run: python experiments/test_ml_weight_evaluation.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.evaluate_ml_weights import (
    parse_match_output, parse_results_csv, merge_metrics,
    make_eval_env, prepare_eval_weights,
    cleanup_eval_weights, compute_verdict, save_result, to_wsl_path,
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

SAMPLE_OUTPUT_NO_SCORE = """
==============================================
  Results  (self-play)
==============================================
  Games          : 30
  P0 wins        :    7  ( 23.3%)
  P1 wins        :    8  ( 26.7%)
  Timeouts       :    0  (  0.0%)
  Errors         :    0  (  0.0%)
  Avg selections : 189.3
  Elapsed        : 95.1s  (3168ms/game)
  Results CSV    : logs/real_20260623.csv
"""
parsed_ns = parse_match_output(SAMPLE_OUTPUT_NO_SCORE)
check("No score: total_score None", parsed_ns["total_score"] is None)

SAMPLE_OUTPUT = """
==============================================
  Results  (self-play)
==============================================
  Games          : 30
  P0 wins        :   15  ( 50.0%)
  P1 wins        :   15  ( 50.0%)
  Timeouts       :    0  (  0.0%)
  Errors         :    0  (  0.0%)
  Avg selections : 189.3
  Total score    : -10
  Score/game     : -0.33
  score=-10
  Elapsed        : 95.1s  (3168ms/game)
  Results CSV    : logs/real_20260623.csv
"""
parsed = parse_match_output(SAMPLE_OUTPUT)
check("Parse games=30", parsed["games"] == 30)
check("Parse wins=15", parsed["wins"] == 15)
check("Parse losses=15", parsed["losses"] == 15)
check("Parse errors=0", parsed["errors"] == 0)
check("Parse timeouts=0", parsed["timeouts"] == 0)
check("Parse avg_selections", parsed["avg_selections"] == 189.3)
check("Parse avg_ms", parsed["avg_ms"] == 3168)
check("Parse results_csv", parsed["results_csv"] == "logs/real_20260623.csv")
check("Parse total_score=-10", parsed["total_score"] == -10.0)

# Positive score
SAMPLE_SCORE = """
  Games          : 10
  P0 wins        :    7
  P1 wins        :    3
  score=40
  Elapsed        : 30.0s  (3000ms/game)
"""
ps = parse_match_output(SAMPLE_SCORE)
check("Parse total_score=40", ps["total_score"] == 40.0)

SAMPLE_ERR = """
  Games          : 30
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
print("\n--- parse_results_csv ---")

with tempfile.TemporaryDirectory() as td:
    csv_path = os.path.join(td, "results.csv")
    with open(csv_path, "w") as f:
        f.write("game,winner,selections\n")
        f.write("g1,p0,100\n")
        f.write("g2,p1,120\n")
        f.write("g3,p0,110\n")
        f.write("g4,,130\n")
    csv_r = parse_results_csv(csv_path)
    check("CSV games=4", csv_r["games"] == 4)
    check("CSV wins=2", csv_r["wins"] == 2)
    check("CSV losses=1", csv_r["losses"] == 1)
    check("CSV draws=1", csv_r["draws"] == 1)
    check("CSV safety all 0", all(v == 0 for v in csv_r["safety"].values()))

    # CSV with safety columns
    csv_safety = os.path.join(td, "safety.csv")
    with open(csv_safety, "w") as f:
        f.write("game,winner,selections,zero_damage_attack,end_with_attack_available\n")
        f.write("g1,p0,100,1,0\n")
        f.write("g2,p1,120,0,2\n")
    csv_sr = parse_results_csv(csv_safety)
    check("Safety zero_damage=1", csv_sr["safety"]["zero_damage_attack"] == 1)
    check("Safety end_with_attack=2", csv_sr["safety"]["end_with_attack_available"] == 2)

check("Nonexistent CSV: no crash", parse_results_csv("/nonexistent.csv")["games"] == 0)

# ===================================================================
print("\n--- merge_metrics ---")

merged_ns = merge_metrics(parsed_ns, "")
check("Merge no score: score_available=False", merged_ns["score_available"] == False)
check("Merge no score: score_per_game=0", merged_ns["score_per_game"] == 0)

merged = merge_metrics(parsed, "")
check("Merge has score_per_game", "score_per_game" in merged)
check("Merge scored: score_available=True", merged["score_available"] == True)
check("Merge score_per_game=-10/30", abs(merged["score_per_game"] - (-10.0/30)) < 0.01)
check("Merge has wins", "wins" in merged)
check("Merge has safety", "safety" in merged)

# With total_score directly
merged_s = merge_metrics({"games": 10, "total_score": 50.0, "avg_selections": 100}, "")
check("Merge score_per_game=5.0", merged_s["score_per_game"] == 5.0)
check("Merge score_available=True", merged_s["score_available"] == True)

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

# BL positive, CD higher -> better (delta > 1.0)
bl = {"errors": 0, "timeouts": 0, "avg_selections": 190, "score_per_game": 2.0,
      "score_available": True, "wins": 10, "losses": 8, "draws": 12, "avg_ms": 3000,
      "safety": {"zero_damage_attack": 0, "end_with_attack_available": 0}}
cd = {"errors": 0, "timeouts": 0, "avg_selections": 195, "score_per_game": 4.0,
      "score_available": True, "wins": 12, "losses": 6, "draws": 12, "avg_ms": 3100,
      "safety": {"zero_damage_attack": 0, "end_with_attack_available": 0}}
v = compute_verdict(bl, cd)
check("BL=2 CD=4: candidate_better", v["verdict"] == "candidate_better")
check("Delta score_per_game=2.0", v["delta"]["score_per_game"] == 2.0)
check("score_pct=100.0", v["delta"]["score_pct"] == 100.0)
check("score_pct_available=True", v["delta"]["score_pct_available"] == True)
check("Delta wins", v["delta"]["wins"] == 2)
check("Delta losses", v["delta"]["losses"] == -2)
check("Delta avg_ms_diff", v["delta"]["avg_ms_diff"] == 100)
check("Delta safety_total_diff=0", v["delta"]["safety_total_diff"] == 0)

# BL=4 CD=2 -> worse (delta < -1.0)
cd_worse = {"errors": 0, "timeouts": 0, "score_per_game": 0.5,
            "score_available": True, "safety": {}}
v_worse = compute_verdict(bl, cd_worse)
check("BL=2 CD=0.5: candidate_worse", v_worse["verdict"] == "candidate_worse")

# BL=2 CD=2.5 -> neutral (delta=0.5, within 1.0)
cd_neutral = {"errors": 0, "timeouts": 0, "score_per_game": 2.5,
              "score_available": True, "safety": {}}
v_neutral = compute_verdict(bl, cd_neutral)
check("BL=2 CD=2.5: neutral (delta=0.5)", v_neutral["verdict"] == "candidate_neutral")

# BL negative, CD=0 -> better (delta=+2.67 > 1.0)
bl_neg = {"errors": 0, "timeouts": 0, "score_per_game": -2.67,
          "score_available": True, "safety": {}}
cd_zero = {"errors": 0, "timeouts": 0, "score_per_game": 0.0,
           "score_available": True, "safety": {}}
v_neg = compute_verdict(bl_neg, cd_zero)
check("BL=-2.67 CD=0: candidate_better", v_neg["verdict"] == "candidate_better")
check("BL neg: score_pct=None", v_neg["delta"]["score_pct"] is None)
check("BL neg: score_pct_available=False", v_neg["delta"]["score_pct_available"] == False)

# BL=0 CD=2.67 -> better (delta=+2.67 > 1.0)
bl_zero_spg = {"errors": 0, "timeouts": 0, "score_per_game": 0.0,
               "score_available": True, "safety": {}}
cd_pos = {"errors": 0, "timeouts": 0, "score_per_game": 2.67,
          "score_available": True, "safety": {}}
v_zero = compute_verdict(bl_zero_spg, cd_pos)
check("BL=0 CD=2.67: candidate_better", v_zero["verdict"] == "candidate_better")
check("BL=0: score_pct=None", v_zero["delta"]["score_pct"] is None)
check("BL=0: score_pct_available=False", v_zero["delta"]["score_pct_available"] == False)

# BL=-2 CD=-4 -> worse (delta=-2.0 < -1.0)
bl_neg2 = {"errors": 0, "timeouts": 0, "score_per_game": -2.0,
           "score_available": True, "safety": {}}
cd_neg4 = {"errors": 0, "timeouts": 0, "score_per_game": -4.0,
           "score_available": True, "safety": {}}
v_neg_worse = compute_verdict(bl_neg2, cd_neg4)
check("BL=-2 CD=-4: candidate_worse", v_neg_worse["verdict"] == "candidate_worse")

# BL=-4 CD=-2 -> better (delta=+2.0 > 1.0)
bl_neg4 = {"errors": 0, "timeouts": 0, "score_per_game": -4.0,
           "score_available": True, "safety": {}}
cd_neg2 = {"errors": 0, "timeouts": 0, "score_per_game": -2.0,
           "score_available": True, "safety": {}}
v_neg_better = compute_verdict(bl_neg4, cd_neg2)
check("BL=-4 CD=-2: candidate_better", v_neg_better["verdict"] == "candidate_better")

# Errors override score
cd_err = {"errors": 1, "timeouts": 0, "score_per_game": 200, "safety": {}}
v_err = compute_verdict(bl, cd_err)
check("Errors -> unsafe even with great score", v_err["verdict"] == "candidate_unsafe")

cd_to = {"errors": 0, "timeouts": 2, "safety": {}}
v_to = compute_verdict(bl, cd_to)
check("Timeouts -> unsafe", v_to["verdict"] == "candidate_unsafe")

# Safety regression overrides score improvement
bl_safe = {"errors": 0, "timeouts": 0, "score_per_game": 2.0, "score_available": True,
           "safety": {"zero_damage_attack": 2}}
cd_regr = {"errors": 0, "timeouts": 0, "score_per_game": 5.0, "score_available": True,
           "safety": {"zero_damage_attack": 5}}
v_regr = compute_verdict(bl_safe, cd_regr)
check("Safety regression overrides score", v_regr["verdict"] == "candidate_safety_regression")

bl_safe0 = {"errors": 0, "timeouts": 0, "score_per_game": 2.0, "score_available": True,
            "safety": {"zero_damage_attack": 0}}
cd_safe1 = {"errors": 0, "timeouts": 0, "score_per_game": 5.0, "score_available": True,
            "safety": {"zero_damage_attack": 1}}
v_regr0 = compute_verdict(bl_safe0, cd_safe1)
check("Safety regression from 0", v_regr0["verdict"] == "candidate_safety_regression")

# No score available
bl_ns = {"errors": 0, "timeouts": 0, "score_available": False, "safety": {}}
cd_ns = {"errors": 0, "timeouts": 0, "score_available": False, "safety": {}}
v_ns = compute_verdict(bl_ns, cd_ns)
check("No score: neutral", v_ns["verdict"] == "candidate_neutral")

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
    check("Has verdict", loaded["verdict"] == "candidate_better")

# ===================================================================
print("\n--- to_wsl_path ---")

r1 = to_wsl_path("C:\\Users\\test\\w.json")
check("C:\\ -> /mnt/c/", r1 == "/mnt/c/Users/test/w.json")
r2 = to_wsl_path("c:\\Users\\test\\w.json")
check("c:\\ -> /mnt/c/", r2 == "/mnt/c/Users/test/w.json")
r3 = to_wsl_path("D:\\data\\file")
check("D:\\ -> /mnt/d/", r3 == "/mnt/d/data/file")
r4 = to_wsl_path("C:/forward/slash")
check("C:/ -> /mnt/c/", r4 == "/mnt/c/forward/slash")

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
