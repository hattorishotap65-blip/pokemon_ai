"""
Automatic heuristic tuning for the Raging Bolt agent.

Two modes:
  --mode tune    : random-perturbation hill climbing over numeric params
  --mode ablate  : disable each rule gate one at a time, measure contribution

Fitness (anti-overfit, per user requirement of no opponent-specific tuning):
  wins over  mirror-vs-baseline (Ng)  +  vs top_lucario (Ng)  +  vs megastarmie (Ng)
Sequential halving: candidates that lose the mirror badly skip the rest.

Usage (inside WSL, run overnight):
  python3 experiments/auto_tune.py --mode tune --iters 12 --games 30 \
      --workdir /tmp/autotune --output experiments/auto_tune_report.json
"""
from __future__ import annotations
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENT_SRC = os.path.join(_REPO, "experiments", "agents", "raging_bolt", "main.py")
PARAMS_SRC = os.path.join(_REPO, "experiments", "agents", "raging_bolt", "params.json")
DECK = os.path.join(_REPO, "experiments", "decks", "raging_bolt_ogerpon.csv")
H2H = os.path.join(_REPO, "experiments", "head_to_head.py")

OPPONENTS = {
    "lucario": (os.path.join(_REPO, "experiments", "agents", "top_lucario_1084_main.py"),
                os.path.join(_REPO, "experiments", "decks", "top_lucario_1084.csv")),
}

# Numeric params to perturb: name -> (default, min, max)
TUNABLE = {
    "attach_for_lethal_score":      (1800, 800, 2600),
    "lillie_pending_defer_score":   (550, 200, 900),
    "catcher_hold_score":           (5, 0, 200),
    "er_hold_score":                (250, 50, 600),
    "er_hold_hand_energy":          (3, 2, 5),
    "energy_pick_need_bonus":       (250, 50, 500),
    "energy_pick_grass_teal_dance": (100, 0, 300),
    "energy_pick_dup_penalty":      (100, 0, 300),
    "energy_retrieval_threshold":   (2, 1, 4),
    "engine_search_top_k":          (5, 3, 8),
    "engine_search_heuristic_weight": (0.15, 0.0, 0.5),
    "se_prize_taken":               (900, 400, 1600),
    "se_prize_given":               (800, 400, 1600),
    "se_bolt_ready":                (350, 100, 800),
    "se_bench_bolt_ready":          (250, 0, 600),
    "se_field_energy":              (60, 10, 150),
    "se_hand_card":                 (40, 10, 100),
    "se_can_ko":                    (400, 100, 900),
}

# Rule gates for ablation: setting to 0 disables the rule
RULE_GATES = [
    "rule_attach_for_lethal",
    "rule_lillie_combo_defer",
    "rule_catcher_hold",
    "rule_er_hold",
]


def load_base_params():
    try:
        with open(PARAMS_SRC, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def make_candidate_dir(workdir, name, params):
    d = os.path.join(workdir, name)
    os.makedirs(d, exist_ok=True)
    shutil.copy(AGENT_SRC, os.path.join(d, "main.py"))
    shutil.copy(DECK, os.path.join(d, "deck.csv"))
    with open(os.path.join(d, "params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f, indent=1)
    return d


def run_match(agent_a_dir, agent_b_spec, n, label_a, label_b, out_json):
    """agent_b_spec: (agent_path, deck_path) or candidate dir."""
    if isinstance(agent_b_spec, tuple):
        b_agent, b_deck = agent_b_spec
    else:
        b_agent = os.path.join(agent_b_spec, "main.py")
        b_deck = os.path.join(agent_b_spec, "deck.csv")
    cmd = [sys.executable, H2H,
           "--agent-a", os.path.join(agent_a_dir, "main.py"), "--deck-a", DECK,
           "--agent-b", b_agent, "--deck-b", b_deck,
           "--label-a", label_a, "--label-b", label_b,
           "--n", str(n), "--output", out_json]
    env = dict(os.environ)
    env.pop("POKEMON_AI_PARAMS_PATH", None)  # params come from each agent's dir
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=n * 90 + 300)
    if r.returncode != 0:
        raise RuntimeError("h2h failed: %s" % r.stderr[-500:])
    with open(out_json, encoding="utf-8") as f:
        return json.load(f)


def evaluate(cand_dir, baseline_dir, games, workdir, tag):
    """Returns (fitness, detail). Sequential halving on the mirror stage."""
    detail = {}
    # Stage 1: mirror vs baseline
    s = run_match(cand_dir, baseline_dir, games, "CAND", "BASE",
                  os.path.join(workdir, f"{tag}_mirror.json"))
    mirror_wins = s["agent_a_wins"]
    detail["mirror"] = f'{mirror_wins}/{games}'
    if mirror_wins < games * 0.38:  # clearly regressed — skip expensive stages
        detail["skipped"] = True
        return mirror_wins, detail
    # Stage 2: vs lucario
    s = run_match(cand_dir, OPPONENTS["lucario"], games, "CAND", "LUC",
                  os.path.join(workdir, f"{tag}_lucario.json"))
    detail["lucario"] = f'{s["agent_a_wins"]}/{games}'
    fitness = mirror_wins + s["agent_a_wins"] * 2  # lucario wins are rarer => weight 2
    # Stage 3: vs megastarmie (fixed copy expected in workdir/megastarmie)
    mega = os.path.join(workdir, "megastarmie")
    if os.path.isdir(mega):
        s = run_match(cand_dir, mega, games, "CAND", "MEGA",
                      os.path.join(workdir, f"{tag}_mega.json"))
        detail["megastarmie"] = f'{s["agent_a_wins"]}/{games}'
        fitness += s["agent_a_wins"]
    return fitness, detail


def perturb(params, rng, k=3):
    """Perturb k random tunables multiplicatively."""
    p = dict(params)
    keys = rng.sample(list(TUNABLE.keys()), k)
    for key in keys:
        default, lo, hi = TUNABLE[key]
        cur = p.get(key, default)
        factor = rng.choice([0.5, 0.7, 1.4, 2.0])
        val = cur * factor if cur else default * factor
        if isinstance(default, int):
            val = int(round(val))
        val = max(lo, min(hi, val))
        p[key] = val
    return p, keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["tune", "ablate"], default="tune")
    ap.add_argument("--iters", type=int, default=12)
    ap.add_argument("--games", type=int, default=30)
    ap.add_argument("--workdir", default="/tmp/autotune")
    ap.add_argument("--output", default=os.path.join(_REPO, "experiments", "auto_tune_report.json"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if sys.platform == "win32":
        print("ERROR: Run inside WSL."); sys.exit(1)

    rng = random.Random(args.seed)
    os.makedirs(args.workdir, exist_ok=True)
    base_params = load_base_params()

    baseline_dir = make_candidate_dir(args.workdir, "baseline", base_params)
    log_path = os.path.join(args.workdir, "tune_log.jsonl")
    results = []

    def log(rec):
        results.append(rec)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps(rec, ensure_ascii=False), flush=True)

    # Baseline fitness
    t0 = time.time()
    base_fit, base_detail = evaluate(baseline_dir, baseline_dir, args.games,
                                     args.workdir, "base_self")
    # mirror vs itself is ~50%; use it only as sanity. Real baseline: lucario+mega stages
    log({"cand": "baseline", "fitness": base_fit, "detail": base_detail,
         "elapsed_min": round((time.time() - t0) / 60, 1)})

    if args.mode == "ablate":
        for gate in RULE_GATES:
            p = dict(base_params); p[gate] = 0
            cand = make_candidate_dir(args.workdir, f"no_{gate}", p)
            t0 = time.time()
            fit, detail = evaluate(cand, baseline_dir, args.games, args.workdir, f"no_{gate}")
            log({"cand": f"no_{gate}", "fitness": fit, "detail": detail,
                 "elapsed_min": round((time.time() - t0) / 60, 1)})
    else:
        best_params = dict(base_params)
        best_fit = base_fit
        for it in range(args.iters):
            cand_params, changed = perturb(best_params, rng)
            cand = make_candidate_dir(args.workdir, f"iter{it}", cand_params)
            t0 = time.time()
            try:
                fit, detail = evaluate(cand, baseline_dir, args.games, args.workdir, f"iter{it}")
            except Exception as ex:
                log({"cand": f"iter{it}", "error": str(ex)[:300]}); continue
            improved = fit > best_fit
            log({"cand": f"iter{it}", "changed": {k: cand_params[k] for k in changed},
                 "fitness": fit, "best_fit": best_fit, "improved": improved,
                 "detail": detail, "elapsed_min": round((time.time() - t0) / 60, 1)})
            if improved:
                best_fit, best_params = fit, cand_params
        with open(os.path.join(args.workdir, "best_params.json"), "w", encoding="utf-8") as f:
            json.dump(best_params, f, indent=1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("Report saved to", args.output)


if __name__ == "__main__":
    main()
