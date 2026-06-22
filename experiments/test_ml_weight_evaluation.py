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

SAMPLE_OUTPUT = """
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
parsed = parse_match_output(SAMPLE_OUTPUT)
check("Parse games=30", parsed["games"] == 30)
check("Parse wins=7", parsed["wins"] == 7)
check("Parse losses=8", parsed["losses"] == 8)
check("Parse errors=0", parsed["errors"] == 0)
check("Parse timeouts=0", parsed["timeouts"] == 0)
check("Parse avg_selections", parsed["avg_selections"] == 189.3)
check("Parse avg_ms", parsed["avg_ms"] == 3168)
check("Parse results_csv", parsed["results_csv"] == "logs/real_20260623.csv")
check("Parse total_score None (no score line)", parsed["total_score"] is None)

# With score line
SAMPLE_SCORE = """
  Games          : 30
  P0 wins        :    7
  P1 wins        :    8
  score=222
  Elapsed        : 95.1s  (3168ms/game)
"""
ps = parse_match_output(SAMPLE_SCORE)
check("Parse total_score=222", ps["total_score"] == 222.0)

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

merged = merge_metrics(parsed, "")
check("Merge has score_per_game", "score_per_game" in merged)
check("Merge no total_score: score_available=False", merged["score_available"] == False)
check("Merge has wins", "wins" in merged)
check("Merge has safety", "safety" in merged)

# With total_score
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

bl = {"errors": 0, "timeouts": 0, "avg_selections": 190, "score_per_game": 100,
      "score_available": True, "wins": 10, "losses": 8, "draws": 12, "avg_ms": 3000,
      "safety": {"zero_damage_attack": 0, "end_with_attack_available": 0}}
cd = {"errors": 0, "timeouts": 0, "avg_selections": 195, "score_per_game": 105,
      "score_available": True, "wins": 12, "losses": 6, "draws": 12, "avg_ms": 3100,
      "safety": {"zero_damage_attack": 0, "end_with_attack_available": 0}}
v = compute_verdict(bl, cd)
check("Verdict better (+5%)", v["verdict"] == "candidate_better")
check("Delta score_per_game", v["delta"]["score_per_game"] == 5.0)
check("Delta score_pct > 0", v["delta"]["score_pct"] > 0)
check("Delta wins", v["delta"]["wins"] == 2)
check("Delta losses", v["delta"]["losses"] == -2)
check("Delta avg_ms_diff", v["delta"]["avg_ms_diff"] == 100)
check("Delta safety_total_diff", v["delta"]["safety_total_diff"] == 0)
check("score_available", v["score_available"] == True)

cd_worse = {"errors": 0, "timeouts": 0, "avg_selections": 185, "score_per_game": 95,
            "score_available": True, "wins": 8, "losses": 12, "draws": 10, "avg_ms": 3000,
            "safety": {}}
v_worse = compute_verdict(bl, cd_worse)
check("Verdict worse (-5%)", v_worse["verdict"] == "candidate_worse")

cd_neutral = {"errors": 0, "timeouts": 0, "avg_selections": 190, "score_per_game": 100.5,
              "score_available": True, "wins": 10, "losses": 8, "draws": 12, "avg_ms": 3000,
              "safety": {}}
v_neutral = compute_verdict(bl, cd_neutral)
check("Verdict neutral (<1%)", v_neutral["verdict"] == "candidate_neutral")

cd_err = {"errors": 1, "timeouts": 0, "avg_selections": 190, "score_per_game": 200, "safety": {}}
v_err = compute_verdict(bl, cd_err)
check("Candidate errors -> unsafe", v_err["verdict"] == "candidate_unsafe")

cd_to = {"errors": 0, "timeouts": 2, "avg_selections": 190, "safety": {}}
v_to = compute_verdict(bl, cd_to)
check("Candidate timeouts -> unsafe", v_to["verdict"] == "candidate_unsafe")

# Safety regression
bl_safe = {"errors": 0, "timeouts": 0, "score_per_game": 100, "score_available": True,
           "safety": {"zero_damage_attack": 2}}
cd_regr = {"errors": 0, "timeouts": 0, "score_per_game": 105, "score_available": True,
           "safety": {"zero_damage_attack": 5}}
v_regr = compute_verdict(bl_safe, cd_regr)
check("Safety regression verdict", v_regr["verdict"] == "candidate_safety_regression")

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
