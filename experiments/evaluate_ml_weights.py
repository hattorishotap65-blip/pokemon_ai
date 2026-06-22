"""
Evaluate trained ML weights against rule-based baseline.

Runs games with baseline (rule_based, no ML) and candidate (hybrid
with ML weights), then compares results.

Usage:
  python experiments/evaluate_ml_weights.py \
      --weights artifacts/ml_policy_weights_outcome_weighted.json \
      --n 30 --start-game 85000 --mode hybrid \
      --output artifacts/ml_weight_eval_result.json
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)


def to_wsl_path(path: str) -> str:
    """Convert Windows absolute path to WSL /mnt/ path."""
    import re
    raw = str(path)
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        drive = raw[0].lower()
        rest = raw[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    p = os.path.abspath(raw)
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return p.replace("\\", "/")


def parse_match_output(stdout: str) -> dict:
    """Parse run_matches_real.py stdout for key metrics."""
    result = {"games": 0, "errors": 0, "timeouts": 0, "avg_ms": 0, "avg_selections": 0}
    for line in stdout.splitlines():
        line = line.strip()
        m = re.search(r"Errors\s*:\s*(\d+)", line)
        if m:
            result["errors"] = int(m.group(1))
        m = re.search(r"Timeouts\s*:\s*(\d+)", line)
        if m:
            result["timeouts"] = int(m.group(1))
        m = re.search(r"Avg selections\s*:\s*([\d.]+)", line)
        if m:
            result["avg_selections"] = float(m.group(1))
        m = re.search(r"(\d+)ms/game", line)
        if m:
            result["avg_ms"] = int(m.group(1))
        m = re.search(r"Elapsed\s*:.*\((\d+)ms/game\)", line)
        if m:
            result["avg_ms"] = int(m.group(1))
    return result


def make_eval_env(mode: str = "rule_based", weights_path: str = "") -> dict:
    """Create environment variables for evaluation run."""
    env = os.environ.copy()
    env["POKEMON_AI_POLICY_MODE"] = mode
    if weights_path:
        env["POKEMON_AI_ML_WEIGHTS_PATH"] = os.path.abspath(weights_path)
    elif "POKEMON_AI_ML_WEIGHTS_PATH" in env:
        del env["POKEMON_AI_ML_WEIGHTS_PATH"]
    return env


def prepare_eval_weights(src_path: str, eval_path: str) -> bool:
    """Copy weights to eval path with enabled=true for evaluation."""
    try:
        with open(src_path, encoding="utf-8") as f:
            data = json.load(f)
        data["enabled"] = True
        os.makedirs(os.path.dirname(eval_path) or ".", exist_ok=True)
        with open(eval_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def cleanup_eval_weights(eval_path: str):
    try:
        if os.path.exists(eval_path):
            os.remove(eval_path)
    except Exception:
        pass


def run_games(n: int, start_game: int, env: dict, use_wsl: bool,
              timeout: int = 900) -> dict:
    """Run games and return parsed results."""
    if use_wsl:
        wsl_root = to_wsl_path(_REPO_ROOT)
        env_exports = ""
        for k in ("POKEMON_AI_POLICY_MODE", "POKEMON_AI_ML_WEIGHTS_PATH"):
            if k in env:
                v = env[k]
                if k == "POKEMON_AI_ML_WEIGHTS_PATH":
                    v = to_wsl_path(v)
                env_exports += f"export {k}='{v}' && "
        cmd = (
            f'wsl -d Ubuntu -e bash -c "'
            f'{env_exports}'
            f'cd {wsl_root} && '
            f'PYTHONPATH={wsl_root}/reference/extracted '
            f'python3 experiments/run_matches_real.py --n {n} --start-game {start_game}"'
        )
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            result = parse_match_output(r.stdout + r.stderr)
            result["games"] = n
            result["returncode"] = r.returncode
            return result
        except subprocess.TimeoutExpired:
            return {"games": n, "errors": 0, "timeouts": n, "avg_ms": 0, "returncode": -1}
    else:
        try:
            r = subprocess.run(
                [sys.executable, "experiments/run_matches_real.py",
                 "--n", str(n), "--start-game", str(start_game)],
                cwd=_REPO_ROOT, capture_output=True, text=True, timeout=timeout, env=env,
            )
            result = parse_match_output(r.stdout + r.stderr)
            result["games"] = n
            result["returncode"] = r.returncode
            return result
        except subprocess.TimeoutExpired:
            return {"games": n, "errors": 0, "timeouts": n, "avg_ms": 0, "returncode": -1}


def compute_verdict(baseline: dict, candidate: dict) -> dict:
    delta = {}
    b_sel = baseline.get("avg_selections", 0)
    c_sel = candidate.get("avg_selections", 0)
    delta["avg_selections_diff"] = round(c_sel - b_sel, 1)

    if candidate["errors"] > 0 or candidate["timeouts"] > 0:
        verdict = "candidate_unsafe"
    elif baseline["errors"] > 0:
        verdict = "baseline_errors"
    else:
        verdict = "candidate_ok"

    return {"delta": delta, "verdict": verdict}


def save_result(path: str, weights_path: str, mode: str,
                baseline: dict, candidate: dict, verdict_info: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    result = {
        "weights_path": weights_path,
        "mode": mode,
        "baseline": baseline,
        "candidate": candidate,
        "delta": verdict_info["delta"],
        "verdict": verdict_info["verdict"],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return result


def main():
    parser = argparse.ArgumentParser(description="Evaluate ML weights vs baseline")
    parser.add_argument("--weights", required=True)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--start-game", type=int, default=85000)
    parser.add_argument("--output", default="artifacts/ml_weight_eval_result.json")
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "ml"])
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--skip-baseline", action="store_true")
    args = parser.parse_args()

    eval_weights_path = os.path.join("artifacts", "_eval_ml_weights_tmp.json")

    if not os.path.exists(args.weights):
        print(f"ERROR: weights file not found: {args.weights}")
        sys.exit(1)

    if not prepare_eval_weights(args.weights, eval_weights_path):
        print(f"ERROR: failed to prepare eval weights")
        sys.exit(1)

    try:
        # Baseline
        if args.skip_baseline:
            baseline = {"games": 0, "errors": 0, "timeouts": 0, "avg_ms": 0, "avg_selections": 0}
            print("Skipping baseline (--skip-baseline)")
        else:
            print(f"Running baseline ({args.n}g, rule_based)...")
            env_bl = make_eval_env("rule_based")
            baseline = run_games(args.n, args.start_game, env_bl, args.use_wsl, args.timeout)
            print(f"  Baseline: errors={baseline['errors']}, timeouts={baseline['timeouts']}, "
                  f"avg_ms={baseline['avg_ms']}")

        # Candidate
        print(f"\nRunning candidate ({args.n}g, {args.mode}, weights={args.weights})...")
        env_cd = make_eval_env(args.mode, eval_weights_path)
        candidate_start = args.start_game + args.n
        candidate = run_games(args.n, candidate_start, env_cd, args.use_wsl, args.timeout)
        print(f"  Candidate: errors={candidate['errors']}, timeouts={candidate['timeouts']}, "
              f"avg_ms={candidate['avg_ms']}")

        verdict_info = compute_verdict(baseline, candidate)
        result = save_result(args.output, args.weights, args.mode, baseline, candidate, verdict_info)

        print(f"\nVerdict: {verdict_info['verdict']}")
        print(f"Result saved to {args.output}")

    finally:
        cleanup_eval_weights(eval_weights_path)


if __name__ == "__main__":
    main()
