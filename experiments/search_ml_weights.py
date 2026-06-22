"""
ML weight mutation search runner.

Generates mutated weight candidates from a base weights JSON,
optionally evaluates them via evaluate_ml_weights.py, and
saves summary.

Usage:
  # Generate only (no evaluation):
  python experiments/search_ml_weights.py \
      --base-weights artifacts/ml_policy_weights_outcome_weighted.json \
      --output-dir artifacts/ml_weight_search \
      --iterations 3 --mutations-per-iteration 3 --no-evaluate

  # Generate + evaluate:
  python experiments/search_ml_weights.py \
      --base-weights artifacts/ml_policy_weights_outcome_weighted.json \
      --output-dir artifacts/ml_weight_search_eval \
      --iterations 1 --mutations-per-iteration 2 \
      --evaluate --n 5 --start-game 86000 --mode hybrid --use-wsl
"""
from __future__ import annotations
import argparse
import copy
import json
import os
import random
import subprocess
import sys
from typing import Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)


def load_weights(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_weights(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clamp_weight(value: float, min_value: float = -10.0, max_value: float = 10.0) -> float:
    return max(min_value, min(max_value, value))


def mutate_weights(
    weights: Dict[str, float],
    mutation_rate: float = 0.2,
    mutation_scale: float = 0.1,
    rng: Optional[random.Random] = None,
) -> Dict[str, float]:
    """Return a new dict with randomly mutated weight values."""
    if rng is None:
        rng = random.Random()
    result = {}
    for k, v in weights.items():
        if rng.random() < mutation_rate:
            result[k] = clamp_weight(v + rng.gauss(0, mutation_scale))
        else:
            result[k] = v
    return result


def make_candidate(
    base_data: dict,
    base_path: str,
    seed: int,
    iteration: int,
    candidate_idx: int,
    mutation_rate: float,
    mutation_scale: float,
) -> dict:
    """Create a candidate weights JSON from base data."""
    rng = random.Random(seed)
    base_weights = base_data.get("weights", {})
    new_weights = mutate_weights(base_weights, mutation_rate, mutation_scale, rng)

    return {
        "enabled": False,
        "mode": "mutated_offline",
        "model_type": base_data.get("model_type", "pairwise_linear_ranker"),
        "weights": {k: round(v, 6) for k, v in sorted(new_weights.items())},
        "mutation": {
            "source": base_path,
            "seed": seed,
            "iteration": iteration,
            "candidate": candidate_idx,
            "mutation_rate": mutation_rate,
            "mutation_scale": mutation_scale,
            "clamp": [-10.0, 10.0],
        },
        "notes": "mutated candidate, disabled by default",
    }


def evaluate_candidate(
    candidate_path: str,
    eval_output_path: str,
    n: int,
    start_game: int,
    mode: str,
    use_wsl: bool,
    timeout: int = 900,
) -> Optional[dict]:
    """Run evaluate_ml_weights.py on a candidate. Returns parsed result or None."""
    cmd = [
        sys.executable, os.path.join(_REPO_ROOT, "experiments", "evaluate_ml_weights.py"),
        "--weights", candidate_path,
        "--n", str(n),
        "--start-game", str(start_game),
        "--output", eval_output_path,
        "--mode", mode,
        "--skip-baseline",
    ]
    if use_wsl:
        cmd.append("--use-wsl")
    try:
        r = subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True, timeout=timeout)
        if os.path.exists(eval_output_path):
            with open(eval_output_path, encoding="utf-8") as f:
                return json.load(f)
    except subprocess.TimeoutExpired:
        return {"verdict": "timeout", "errors": 0, "timeouts": n}
    except Exception:
        pass
    return None


def rank_candidates(candidates: List[dict]) -> List[dict]:
    """Rank candidates: prefer safe, then best score_per_game_delta."""
    def sort_key(c):
        unsafe = 1 if c.get("verdict") in ("candidate_unsafe", "eval_failed", "timeout") else 0
        errors = c.get("errors", 999)
        timeouts = c.get("timeouts", 999)
        spg = c.get("score_per_game_delta", 0) or 0
        spct = c.get("score_pct", 0) or 0
        return (unsafe, errors, timeouts, -spg, -spct)
    return sorted(candidates, key=sort_key)


def build_summary(
    base_path: str,
    output_dir: str,
    iterations: int,
    mutations_per: int,
    mutation_rate: float,
    mutation_scale: float,
    evaluated: bool,
    candidate_results: List[dict],
    top_k: int = 3,
) -> dict:
    ranked = rank_candidates(candidate_results) if evaluated and candidate_results else []
    best = ranked[:top_k] if ranked else []
    return {
        "base_weights": base_path,
        "iterations": iterations,
        "mutations_per_iteration": mutations_per,
        "mutation_rate": mutation_rate,
        "mutation_scale": mutation_scale,
        "evaluated": evaluated,
        "total_candidates": len(candidate_results),
        "candidates": candidate_results,
        "best_candidates": [
            {"path": c["path"], "verdict": c.get("verdict", "not_evaluated"),
             "errors": c.get("errors", 0), "timeouts": c.get("timeouts", 0)}
            for c in best
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="ML weight mutation search")
    parser.add_argument("--base-weights", required=True)
    parser.add_argument("--output-dir", default="artifacts/ml_weight_search")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--mutations-per-iteration", type=int, default=5)
    parser.add_argument("--mutation-rate", type=float, default=0.2)
    parser.add_argument("--mutation-scale", type=float, default=0.1)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--evaluate", dest="evaluate", action="store_true")
    parser.add_argument("--no-evaluate", dest="evaluate", action="store_false")
    parser.set_defaults(evaluate=False)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--start-game", type=int, default=86000)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "ml"])
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    do_eval = args.evaluate

    if not os.path.exists(args.base_weights):
        print(f"ERROR: base weights not found: {args.base_weights}")
        sys.exit(1)

    base_data = load_weights(args.base_weights)
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Base weights: {args.base_weights}")
    print(f"Output dir: {args.output_dir}")
    print(f"Iterations: {args.iterations}, Mutations/iter: {args.mutations_per_iteration}")
    print(f"Mutation rate: {args.mutation_rate}, scale: {args.mutation_scale}")
    print(f"Evaluate: {do_eval}")

    candidate_results = []
    candidate_num = 0
    game_offset = 0

    for it in range(args.iterations):
        for mi in range(args.mutations_per_iteration):
            candidate_num += 1
            seed = args.seed + candidate_num
            cand_name = f"candidate_{candidate_num:04d}"
            cand_path = os.path.join(args.output_dir, f"{cand_name}.json")

            cand_data = make_candidate(
                base_data, args.base_weights, seed,
                it + 1, mi + 1, args.mutation_rate, args.mutation_scale,
            )
            save_weights(cand_path, cand_data)

            result_entry = {
                "path": f"{cand_name}.json",
                "iteration": it + 1,
                "candidate": mi + 1,
                "seed": seed,
            }

            if do_eval:
                eval_path = os.path.join(args.output_dir, f"eval_{cand_name}.json")
                start = args.start_game + game_offset
                game_offset += args.n * 2

                print(f"  Evaluating {cand_name} (start={start})...")
                eval_result = evaluate_candidate(
                    cand_path, eval_path, args.n, start,
                    args.mode, args.use_wsl, args.timeout,
                )
                if eval_result:
                    cand_info = eval_result.get("candidate", {})
                    delta = eval_result.get("delta", {})
                    result_entry["eval_path"] = f"eval_{cand_name}.json"
                    result_entry["verdict"] = eval_result.get("verdict", "unknown")
                    result_entry["errors"] = cand_info.get("errors", 0)
                    result_entry["timeouts"] = cand_info.get("timeouts", 0)
                    result_entry["avg_selections_diff"] = delta.get("avg_selections_diff", 0)
                    result_entry["score_per_game_delta"] = delta.get("score_per_game", 0)
                    result_entry["score_pct"] = delta.get("score_pct", 0)
                    result_entry["wins_delta"] = delta.get("wins", 0)
                    result_entry["losses_delta"] = delta.get("losses", 0)
                else:
                    result_entry["verdict"] = "eval_failed"
            else:
                result_entry["verdict"] = "not_evaluated"

            candidate_results.append(result_entry)
            print(f"  {cand_name}: {result_entry['verdict']}")

    summary = build_summary(
        args.base_weights, args.output_dir,
        args.iterations, args.mutations_per_iteration,
        args.mutation_rate, args.mutation_scale,
        do_eval, candidate_results, args.top_k,
    )
    summary_path = os.path.join(args.output_dir, "summary.json")
    save_weights(summary_path, summary)
    print(f"\nSummary saved to {summary_path}")
    print(f"Total candidates: {candidate_num}")
    if do_eval and summary["best_candidates"]:
        print(f"Best candidates: {[c['path'] for c in summary['best_candidates']]}")


if __name__ == "__main__":
    main()
