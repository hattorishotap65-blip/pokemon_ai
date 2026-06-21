"""
Level 6: Minimal weight search script.

Runs small-scale simulations with different weight configurations and
compares anomaly metrics against a baseline.

Usage:
  python experiments/weight_search.py --games 30 --output reports
  python experiments/weight_search.py --games 50 --output reports --patterns 3
  python experiments/weight_search.py --games 30 --use-wsl
"""
import argparse
import json
import os
import sys
import shutil
import subprocess
import itertools
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _to_wsl_path(path: str) -> str:
    """Convert a path to WSL-compatible format. Handles both Windows and Linux paths."""
    if path.startswith("/"):
        return path
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        rest = path[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return path
_WEIGHTS_PATH = os.path.join(_REPO_ROOT, "data", "weights.json")
_INBOX = os.path.join(_REPO_ROOT, "battle_logs", "inbox")
_LOGS = os.path.join(_REPO_ROOT, "logs")

# Weight keys used for scoring (read from data/weights.json at runtime)
_WEIGHT_KEYS = [
    "advantage_weight",
    "energy_to_plan_bonus",
    "energy_to_plan_bonus_no_need",
    "attack_suppress_penalty",
    "retreat_to_better_attacker_bonus",
    "voltorb_ko_attack_bonus",
    "voltorb_damage_scaling",
]


def _load_baseline() -> dict:
    """Load current baseline from data/weights.json."""
    if os.path.exists(_WEIGHTS_PATH):
        with open(_WEIGHTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k: data[k] for k in _WEIGHT_KEYS if k in data}
    return {}


# Fallback search grid (used when no --grid-file is given)
_SEARCH_GRID = {
    "advantage_weight": [0.2, 0.3, 0.4, 0.5, 0.6],
    "energy_to_plan_bonus": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
    "energy_to_plan_bonus_no_need": [1.0, 2.0, 3.0, 4.0],
    "voltorb_ko_attack_bonus": [500.0, 750.0, 1000.0, 1250.0, 1500.0],
    "voltorb_damage_scaling": [0.4, 0.6, 0.8, 1.0, 1.2],
}


def _read_weights() -> dict:
    """Read current weights.json content for backup."""
    if os.path.exists(_WEIGHTS_PATH):
        with open(_WEIGHTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_weights(weights: dict):
    """Write weights to data/weights.json."""
    data = {"schema_version": "1.0"}
    data.update(weights)
    with open(_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _restore_weights(backup: dict):
    """Restore weights.json from backup."""
    if backup:
        with open(_WEIGHTS_PATH, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2)


def _run_simulation(games: int, start_game: int, use_wsl: bool) -> bool:
    """Run simulation. Returns True on success."""
    if use_wsl:
        wsl_root = _to_wsl_path(_REPO_ROOT)
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
            cwd=_REPO_ROOT,
            capture_output=True, text=True, timeout=600, env=env,
        )
    return result.returncode == 0


def _run_anomaly_detection(start_id: int, count: int, output_dir: str) -> dict:
    """Run anomaly detection on logs from start_id to start_id+count-1."""
    import glob
    os.makedirs(_INBOX, exist_ok=True)
    for gid in range(start_id, start_id + count):
        src = os.path.join(_LOGS, f"game_g{gid:04d}.jsonl")
        if os.path.exists(src):
            shutil.copy(src, _INBOX)

    subprocess.run(
        [sys.executable, "tools/analyze_battle_logs.py",
         "--input", "battle_logs/inbox",
         "--output", output_dir,
         "--deck-profile", "data/deck_profile.json",
         "--top", "20"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )

    for f in glob.glob(os.path.join(_INBOX, "*.jsonl")):
        os.remove(f)

    rpt_path = os.path.join(_REPO_ROOT, output_dir, "latest_anomaly_report.json")
    if os.path.exists(rpt_path):
        with open(rpt_path) as f:
            return json.load(f)
    return {}


def _extract_metrics(report: dict) -> dict:
    s = report.get("summary", {})
    return {
        "games": s.get("games", 0),
        "anomalies_total": s.get("anomalies_total", 0),
        "attack_available_but_no_attack": s.get("attack_available_but_no_attack", 0),
        "end_when_attack_available": s.get("end_when_attack_available", 0),
        "retreat_when_attack_available": s.get("retreat_when_attack_available", 0),
        "best_damage_attacker_not_selected": s.get("best_damage_attacker_not_selected", 0),
    }


def main():
    parser = argparse.ArgumentParser(description="Level 6: Weight search")
    parser.add_argument("--games", type=int, default=30, help="Games per pattern")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--patterns", type=int, default=0, help="Max patterns to test (0=all)")
    parser.add_argument("--use-wsl", action="store_true", help="Run simulation via WSL")
    parser.add_argument("--start-game", type=int, default=4000, help="Starting game ID")
    parser.add_argument("--grid-file", default=None, help="JSON file with custom pattern list")
    args = parser.parse_args()

    baseline = _load_baseline()

    if args.grid_file and os.path.exists(args.grid_file):
        with open(args.grid_file, encoding="utf-8") as f:
            grid_data = json.load(f)
        all_patterns = []
        for p in grid_data.get("patterns", []):
            w = dict(baseline)
            w.update(p)
            all_patterns.append(w)
        keys = sorted(set(k for p in grid_data.get("patterns", []) for k in p.keys()))
    else:
        keys = sorted(_SEARCH_GRID.keys())
        values = [_SEARCH_GRID[k] for k in keys]
        all_patterns = []
        for combo in itertools.product(*values):
            w = dict(baseline)
            for k, v in zip(keys, combo):
                w[k] = v
            all_patterns.append(w)

    if args.patterns > 0:
        all_patterns = all_patterns[:args.patterns]

    print(f"Weight search: {len(all_patterns)} patterns x {args.games} games")
    print(f"WSL: {'yes' if args.use_wsl else 'no'}\n")

    # Backup current weights.json
    weights_backup = _read_weights()

    results = []
    start_game = args.start_game

    try:
        for i, pattern in enumerate(all_patterns):
            label = " | ".join(f"{k}={pattern[k]}" for k in keys)
            print(f"[{i+1}/{len(all_patterns)}] {label}")

            _write_weights(pattern)

            ok = _run_simulation(args.games, start_game, args.use_wsl)
            if not ok:
                print(f"  FAILED - skipping")
                start_game += args.games
                continue

            out_dir = os.path.join(args.output, f"weight_search_{i:02d}")
            os.makedirs(os.path.join(_REPO_ROOT, out_dir), exist_ok=True)
            report = _run_anomaly_detection(start_game, args.games, out_dir)
            metrics = _extract_metrics(report)

            result = {"pattern_id": i, "weights": {k: pattern[k] for k in keys}, "metrics": metrics}
            results.append(result)
            games = metrics.get("games", 0)
            anomalies = metrics.get("anomalies_total", 0)
            per_game = anomalies / games if games else 0
            print(f"  {games}g | anomalies={anomalies} ({per_game:.2f}/g) | "
                  f"safety: atk={metrics.get('attack_available_but_no_attack',0)} "
                  f"end={metrics.get('end_when_attack_available',0)} "
                  f"ret={metrics.get('retreat_when_attack_available',0)}")

            start_game += args.games

    finally:
        _restore_weights(weights_backup)
        print(f"\nweights.json restored to pre-search state.")

    # Save results
    out_base = os.path.join(_REPO_ROOT, args.output)
    os.makedirs(out_base, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_base, f"level6_weight_search_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "schema_version": "1.0",
            "search_grid": _SEARCH_GRID,
            "baseline": baseline,
            "games_per_pattern": args.games,
            "results": results,
        }, f, indent=2)

    baseline_path = os.path.join(out_base, "level6_weight_search_baseline.json")
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump({
            "schema_version": "1.0",
            "search_grid": _SEARCH_GRID,
            "baseline": baseline,
            "games_per_pattern": args.games,
            "patterns_tested": len(results),
            "results": results,
        }, f, indent=2)

    print(f"Results saved: {out_path}")

    if results:
        print(f"\n{'='*70}")
        print(f"{'Pattern':<40s} {'Games':>5s} {'Anom':>5s} {'/g':>5s} {'Safe':>4s}")
        print("-" * 70)
        for r in sorted(results, key=lambda x: x["metrics"].get("anomalies_total", 9999)):
            m = r["metrics"]
            g = m.get("games", 0)
            a = m.get("anomalies_total", 0)
            pg = a / g if g else 0
            safe = (m.get("attack_available_but_no_attack", 0) == 0
                    and m.get("end_when_attack_available", 0) == 0
                    and m.get("retreat_when_attack_available", 0) == 0)
            label = " | ".join(f"{k}={r['weights'][k]}" for k in keys)
            print(f"  {label:<38s} {g:5d} {a:5d} {pg:5.2f} {'OK' if safe else 'NG':>4s}")


if __name__ == "__main__":
    main()
