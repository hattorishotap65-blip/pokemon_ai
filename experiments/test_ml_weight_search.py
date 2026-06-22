"""
Tests for experiments/search_ml_weights.py.

Run: python experiments/test_ml_weight_search.py
"""
import sys, os, json, tempfile, copy, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.search_ml_weights import (
    load_weights, save_weights, clamp_weight, mutate_weights,
    make_candidate, rank_candidates, build_summary,
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

BASE_DATA = {
    "enabled": False,
    "mode": "trained_offline",
    "model_type": "pairwise_linear_ranker",
    "weights": {"is_attack": 0.5, "can_ko": 1.2, "is_end": -0.3},
}

# ===================================================================
print("\n--- load / save weights ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "w.json")
    save_weights(path, BASE_DATA)
    check("Save creates file", os.path.exists(path))

    loaded = load_weights(path)
    check("Load returns dict", isinstance(loaded, dict))
    check("Weights preserved", loaded["weights"]["is_attack"] == 0.5)

    with open(path) as f:
        raw = json.loads(f.read())
    check("Valid JSON", isinstance(raw, dict))

# ===================================================================
print("\n--- clamp_weight ---")

check("Within range unchanged", clamp_weight(5.0) == 5.0)
check("Clamp upper", clamp_weight(15.0) == 10.0)
check("Clamp lower", clamp_weight(-15.0) == -10.0)
check("Custom range", clamp_weight(5.0, -1.0, 1.0) == 1.0)

# ===================================================================
print("\n--- mutate_weights ---")

orig = {"a": 1.0, "b": 2.0, "c": 3.0}
orig_copy = copy.deepcopy(orig)
rng = random.Random(42)
mutated = mutate_weights(orig, mutation_rate=1.0, mutation_scale=0.1, rng=rng)

check("Original unchanged", orig == orig_copy)
check("Same keys", set(mutated.keys()) == set(orig.keys()))
check("Values differ (rate=1.0)", mutated != orig)
check("All values numeric", all(isinstance(v, float) for v in mutated.values()))
check("All within clamp", all(-10.0 <= v <= 10.0 for v in mutated.values()))

# rate=0.0 means no mutation
no_mut = mutate_weights(orig, mutation_rate=0.0, mutation_scale=1.0)
check("Rate 0: no mutation", no_mut == orig)

# ===================================================================
print("\n--- make_candidate ---")

cand = make_candidate(BASE_DATA, "base.json", seed=123, iteration=1,
                      candidate_idx=2, mutation_rate=0.2, mutation_scale=0.1)
check("Candidate enabled=False", cand["enabled"] == False)
check("Candidate mode", cand["mode"] == "mutated_offline")
check("Has weights", "weights" in cand and len(cand["weights"]) > 0)
check("Has mutation metadata", "mutation" in cand)
check("Mutation source", cand["mutation"]["source"] == "base.json")
check("Mutation seed", cand["mutation"]["seed"] == 123)
check("Mutation iteration", cand["mutation"]["iteration"] == 1)
check("Mutation candidate", cand["mutation"]["candidate"] == 2)
check("Same key set", set(cand["weights"].keys()) == set(BASE_DATA["weights"].keys()))
check("JSON serializable", isinstance(json.dumps(cand), str))

# ===================================================================
print("\n--- rank_candidates ---")

cands = [
    {"path": "c1.json", "verdict": "candidate_neutral", "errors": 0, "timeouts": 0,
     "score_per_game_delta": 2.0, "score_pct": 3.0},
    {"path": "c2.json", "verdict": "candidate_unsafe", "errors": 1, "timeouts": 0,
     "score_per_game_delta": 10.0, "score_pct": 15.0},
    {"path": "c3.json", "verdict": "candidate_better", "errors": 0, "timeouts": 0,
     "score_per_game_delta": 5.0, "score_pct": 8.0},
    {"path": "c4.json", "verdict": "candidate_neutral", "errors": 0, "timeouts": 1,
     "score_per_game_delta": 3.0, "score_pct": 5.0},
]
ranked = rank_candidates(cands)
check("Best: highest score_per_game_delta (c3)", ranked[0]["path"] == "c3.json")
check("Second: c1 (safe, lower spg delta)", ranked[1]["path"] == "c1.json")
check("Unsafe last", ranked[-1]["verdict"] == "candidate_unsafe")

# No score metrics
cands_no_score = [
    {"path": "a.json", "verdict": "candidate_neutral", "errors": 0, "timeouts": 0},
    {"path": "b.json", "verdict": "eval_failed", "errors": 0, "timeouts": 0},
]
ranked_ns = rank_candidates(cands_no_score)
check("No score: safe first", ranked_ns[0]["path"] == "a.json")
check("eval_failed last", ranked_ns[-1]["path"] == "b.json")

# score_pct=None does not crash
cands_pct_none = [
    {"path": "n1.json", "verdict": "candidate_better", "errors": 0, "timeouts": 0,
     "score_per_game_delta": 3.0, "score_pct": None},
    {"path": "n2.json", "verdict": "candidate_neutral", "errors": 0, "timeouts": 0,
     "score_per_game_delta": 1.0, "score_pct": None},
]
ranked_pn = rank_candidates(cands_pct_none)
check("score_pct=None: no crash", ranked_pn[0]["path"] == "n1.json")
check("score_pct=None: ranked by spg_delta", ranked_pn[1]["path"] == "n2.json")

# Safety regression ranked down
cands_sr = [
    {"path": "ok.json", "verdict": "candidate_neutral", "errors": 0, "timeouts": 0},
    {"path": "sr.json", "verdict": "candidate_safety_regression", "errors": 0, "timeouts": 0},
]
ranked_sr = rank_candidates(cands_sr)
check("Safety regression ranked below neutral", ranked_sr[0]["path"] == "ok.json")

# ===================================================================
print("\n--- build_summary ---")

summary = build_summary(
    "base.json", "output/", 2, 3, 0.2, 0.1, True, cands, top_k=2,
)
check("Summary has base_weights", summary["base_weights"] == "base.json")
check("Summary has iterations", summary["iterations"] == 2)
check("Summary evaluated", summary["evaluated"] == True)
check("Summary candidates", len(summary["candidates"]) == 4)
check("Best candidates <= 2", len(summary["best_candidates"]) <= 2)
check("Summary JSON serializable", isinstance(json.dumps(summary), str))

# Not evaluated
summary_ne = build_summary("base.json", "out/", 1, 1, 0.2, 0.1, False, [], 3)
check("No eval: best empty", len(summary_ne["best_candidates"]) == 0)

# ===================================================================
print("\n--- evaluate flag parsing ---")

import argparse
from experiments.search_ml_weights import main as _main_ref
# Re-create parser logic inline to test flag behavior
def _parse_eval_flag(args_list):
    p = argparse.ArgumentParser()
    p.add_argument("--evaluate", dest="evaluate", action="store_true")
    p.add_argument("--no-evaluate", dest="evaluate", action="store_false")
    p.set_defaults(evaluate=False)
    return p.parse_args(args_list)

check("Default: evaluate=False", _parse_eval_flag([]).evaluate == False)
check("--evaluate: True", _parse_eval_flag(["--evaluate"]).evaluate == True)
check("--no-evaluate: False", _parse_eval_flag(["--no-evaluate"]).evaluate == False)
check("--evaluate --no-evaluate: last wins (False)", _parse_eval_flag(["--evaluate", "--no-evaluate"]).evaluate == False)

# ===================================================================
print("\n--- configs not modified ---")

cfg_path = os.path.join(os.path.dirname(__file__), "..", "configs", "ml_policy_weights.json")
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        cfg = json.load(f)
    check("configs enabled=false", cfg["enabled"] == False)
    check("configs weights empty", cfg["weights"] == {})

# ===================================================================
print("\n--- end-to-end candidate generation ---")

with tempfile.TemporaryDirectory() as td:
    base_path = os.path.join(td, "base.json")
    save_weights(base_path, BASE_DATA)

    results = []
    for i in range(3):
        cand = make_candidate(BASE_DATA, base_path, seed=42+i, iteration=1,
                              candidate_idx=i+1, mutation_rate=0.3, mutation_scale=0.05)
        cand_path = os.path.join(td, f"candidate_{i+1:04d}.json")
        save_weights(cand_path, cand)
        results.append({"path": f"candidate_{i+1:04d}.json", "verdict": "not_evaluated"})

    check("3 candidates created", len(results) == 3)
    check("All files exist", all(os.path.exists(os.path.join(td, r["path"])) for r in results))

    for r in results:
        with open(os.path.join(td, r["path"])) as f:
            d = json.load(f)
        check(f"{r['path']}: enabled=false", d["enabled"] == False)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
