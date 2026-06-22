"""
Core parameter search runner.

Generates candidate sets from the 5 externalized core params,
writes temporary config files, and records evaluation results.

Usage:
  # Generate candidates only (dry-run):
  python scripts/run_core_param_search.py --dry-run

  # Run evaluation (requires WSL):
  python scripts/run_core_param_search.py --games 30 --start-game 40000 --use-wsl
"""
from __future__ import annotations
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SEARCHABLE = os.path.join(_REPO_ROOT, "configs", "params", "searchable_params.json")
_DENY = os.path.join(_REPO_ROOT, "configs", "params", "deny_params.json")
_DEFAULT = os.path.join(_REPO_ROOT, "configs", "params", "default_params.json")

_CORE_PARAMS = [
    "zero_damage_attack_penalty",
    "ko_opponent_bonus",
    "boss_can_ko",
    "alt_attacker_ko_score",
    "energy_ready_bonus",
]


def _load_searchable():
    with open(_SEARCHABLE, encoding="utf-8") as f:
        data = json.load(f)
    return {p["name"]: p for p in data["params"] if p["name"] in _CORE_PARAMS}


def _load_deny():
    try:
        with open(_DENY, encoding="utf-8") as f:
            data = json.load(f)
        return {p["name"] for p in data["params"]}
    except Exception:
        return set()


def generate_candidates(params: dict, n_random: int = 3) -> list:
    """Generate candidate sets: baseline + per-param low/high + random."""
    baseline = {name: p["current"] for name, p in params.items()}
    candidates = [{"id": "baseline", "params": dict(baseline)}]

    for name, p in params.items():
        rng = p["range"]
        current = p["current"]
        low = min(v for v in rng if v < current) if any(v < current for v in rng) else current
        high = max(v for v in rng if v > current) if any(v > current for v in rng) else current
        if low != current:
            c = dict(baseline)
            c[name] = low
            candidates.append({"id": f"{name}_low_{low}", "params": c})
        if high != current:
            c = dict(baseline)
            c[name] = high
            candidates.append({"id": f"{name}_high_{high}", "params": c})

    for i in range(n_random):
        c = {}
        for name, p in params.items():
            c[name] = random.choice(p["range"])
        candidates.append({"id": f"random_{i}", "params": c})

    return candidates


def write_temp_config(candidate: dict, path: str):
    config = {"schema_version": "1.0"}
    config.update(candidate["params"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def run_evaluation(games: int, start_game: int, use_wsl: bool) -> dict:
    """Run simulation and return metrics. Handles timeout gracefully."""
    metrics = {"games": games, "errors": 0, "timeouts": 0}
    try:
        if use_wsl:
            wsl_root = f"/mnt/c{_REPO_ROOT[2:].replace(os.sep, '/')}"
            cmd = (
                f'wsl -d Ubuntu -e bash -c '
                f'"cd {wsl_root} && '
                f'PYTHONPATH={wsl_root}/reference/extracted '
                f'python3 experiments/run_matches_real.py --n {games} --start-game {start_game}"'
            )
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        else:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.path.join(_REPO_ROOT, "reference", "extracted")
            result = subprocess.run(
                [sys.executable, "experiments/run_matches_real.py",
                 "--n", str(games), "--start-game", str(start_game)],
                cwd=_REPO_ROOT, capture_output=True, text=True, timeout=600, env=env,
            )
    except subprocess.TimeoutExpired:
        print("  WARNING: simulation timed out, skipping candidate")
        metrics["timeouts"] = games
        return metrics
    for line in (result.stdout or "").split("\n"):
        if "Errors" in line:
            try:
                metrics["errors"] = int(line.split(":")[1].strip().split()[0])
            except Exception:
                pass
        if "Timeouts" in line:
            try:
                metrics["timeouts"] = int(line.split(":")[1].strip().split()[0])
            except Exception:
                pass
    return metrics


def run_anomaly_detection(start_game: int, count: int) -> dict:
    """Run anomaly detection and return summary."""
    inbox = os.path.join(_REPO_ROOT, "battle_logs", "inbox")
    logs_dir = os.path.join(_REPO_ROOT, "logs")
    os.makedirs(inbox, exist_ok=True)

    for gid in range(start_game, start_game + count):
        src = os.path.join(logs_dir, f"game_g{gid:05d}.jsonl")
        if os.path.exists(src):
            shutil.copy(src, inbox)

    try:
        subprocess.run(
            [sys.executable, "tools/analyze_battle_logs.py",
             "--input", "battle_logs/inbox", "--output", "reports",
             "--deck-profile", "data/deck_profile.json", "--top", "20"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("  WARNING: anomaly detection timed out")

    import glob
    for f in glob.glob(os.path.join(inbox, "*.jsonl")):
        os.remove(f)

    rpt = os.path.join(_REPO_ROOT, "reports", "latest_anomaly_report.json")
    if os.path.exists(rpt):
        with open(rpt) as f:
            data = json.load(f)
        s = data.get("summary", {})
        g = max(s.get("games", 1), 1)
        return {
            "anomalies_total": s.get("anomalies_total", 0),
            "anomalies_per_game": round(s.get("anomalies_total", 0) / g, 2),
            "attack_no_attack": s.get("attack_available_but_no_attack", 0),
            "end_with_attack": s.get("end_when_attack_available", 0),
            "retreat_with_attack": s.get("retreat_when_attack_available", 0),
        }
    return {}


def format_csv(results: list) -> str:
    header = "candidate_id," + ",".join(_CORE_PARAMS) + ",anomalies_per_game,errors,timeouts,safety_ok"
    lines = [header]
    for r in results:
        vals = ",".join(str(r["params"].get(p, "")) for p in _CORE_PARAMS)
        safety = r.get("attack_no_attack", 0) == 0 and r.get("end_with_attack", 0) == 0
        lines.append(f'{r["id"]},{vals},{r.get("anomalies_per_game","")},{r.get("errors","")},{r.get("timeouts","")},{"OK" if safety else "NG"}')
    return "\n".join(lines)


def format_markdown(results: list) -> str:
    lines = ["# Core Parameter Search Report", "",
             f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}", "",
             "| ID | " + " | ".join(_CORE_PARAMS) + " | APG | Errors | Safety |",
             "|" + "|".join(["---"] * (len(_CORE_PARAMS) + 4)) + "|"]
    for r in results:
        vals = " | ".join(str(r["params"].get(p, "")) for p in _CORE_PARAMS)
        safety = "OK" if r.get("attack_no_attack", 0) == 0 and r.get("end_with_attack", 0) == 0 else "NG"
        lines.append(f'| {r["id"]} | {vals} | {r.get("anomalies_per_game","-")} | {r.get("errors","-")} | {safety} |')
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Core parameter search runner")
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--start-game", type=int, default=40000)
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--n-random", type=int, default=3)
    args = parser.parse_args()

    deny = _load_deny()
    params = _load_searchable()
    for name in list(params.keys()):
        if name in deny:
            del params[name]
            print(f"  DENIED: {name}")

    candidates = generate_candidates(params, args.n_random)
    print(f"Generated {len(candidates)} candidates")
    for c in candidates:
        print(f"  {c['id']}: {c['params']}")

    if args.dry_run:
        print("\n[DRY-RUN] No games executed.")
        results_dir = os.path.join(_REPO_ROOT, "experiments", "results")
        os.makedirs(results_dir, exist_ok=True)
        csv_path = os.path.join(results_dir, "core_param_search.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(format_csv(candidates))
        print(f"Candidates CSV: {csv_path}")
        return

    backup_path = _DEFAULT + ".backup"
    shutil.copy(_DEFAULT, backup_path)

    results = []
    game_cursor = args.start_game

    try:
        for c in candidates:
            print(f"\n--- {c['id']} ---")
            write_temp_config(c, _DEFAULT)

            metrics = run_evaluation(args.games, game_cursor, args.use_wsl)
            if metrics.get("timeouts", 0) == args.games:
                c.update(metrics)
                c["anomalies_per_game"] = "-"
                results.append(c)
                print(f"  SKIPPED (timeout)")
                game_cursor += args.games
                continue

            anomalies = run_anomaly_detection(game_cursor, args.games)

            c.update(metrics)
            c.update(anomalies)
            results.append(c)

            apg = c.get("anomalies_per_game", "-")
            print(f"  APG: {apg}, errors: {c.get('errors',0)}, timeouts: {c.get('timeouts',0)}")

            game_cursor += args.games
    finally:
        shutil.copy(backup_path, _DEFAULT)
        if os.path.exists(backup_path):
            os.remove(backup_path)
        print(f"\ndefault_params.json restored.")

        results_dir = os.path.join(_REPO_ROOT, "experiments", "results")
        os.makedirs(results_dir, exist_ok=True)

        if results:
            csv_path = os.path.join(results_dir, "core_param_search.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(format_csv(results))
            print(f"CSV: {csv_path}")

            md_path = os.path.join(_REPO_ROOT, "docs", "core_param_search_report.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(format_markdown(results))
            print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
