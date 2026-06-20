"""
Level 6: Minimal weight search script.

Runs small-scale simulations with different weight configurations and
compares anomaly metrics against a baseline.

Usage:
  python experiments/weight_search.py --games 30 --output reports
  python experiments/weight_search.py --games 50 --output reports --patterns 3
"""
import argparse
import json
import os
import sys
import shutil
import subprocess
import itertools
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "weights.json")
_INBOX = os.path.join(os.path.dirname(__file__), "..", "battle_logs", "inbox")
_LOGS = os.path.join(os.path.dirname(__file__), "..", "logs")

# Default weights (must match data/weights.json initial values)
_DEFAULTS = {
    "advantage_weight": 0.4,
    "energy_to_plan_bonus": 5.0,
    "energy_to_plan_bonus_no_need": 2.0,
    "attack_suppress_penalty": -30.0,
}

# Search grid (small — expand later)
_SEARCH_GRID = {
    "advantage_weight": [0.3, 0.4, 0.5],
    "energy_to_plan_bonus": [3.0, 5.0, 7.0],
}


def _write_weights(weights: dict):
    """Write weights to data/weights.json."""
    data = {"schema_version": "1.0"}
    data.update(weights)
    with open(_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _restore_defaults():
    _write_weights(_DEFAULTS)


def _run_simulation(games: int, start_game: int) -> bool:
    """Run simulation via WSL. Returns True on success."""
    cmd = (
        f'wsl -d Ubuntu -e bash -c '
        f'"cd /mnt/c/Users/shclo/projects/pokemon_card_ai && '
        f'PYTHONPATH=/mnt/c/Users/shclo/projects/pokemon_card_ai/reference/extracted '
        f'python3 experiments/run_matches_real.py --n {games} --start-game {start_game}"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    return result.returncode == 0


def _run_anomaly_detection(log_prefix: str, output_dir: str) -> dict:
    """Run anomaly detection on logs matching prefix."""
    import glob
    # Copy logs to inbox
    os.makedirs(_INBOX, exist_ok=True)
    for f in glob.glob(os.path.join(_LOGS, f"game_{log_prefix}*.jsonl")):
        shutil.copy(f, _INBOX)

    # Run detection
    cmd = [
        sys.executable, "tools/analyze_battle_logs.py",
        "--input", "battle_logs/inbox",
        "--output", output_dir,
        "--deck-profile", "data/deck_profile.json",
        "--top", "20",
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    # Clean inbox
    for f in glob.glob(os.path.join(_INBOX, "*.jsonl")):
        os.remove(f)

    # Load report
    rpt_path = os.path.join(output_dir, "latest_anomaly_report.json")
    if os.path.exists(rpt_path):
        with open(rpt_path) as f:
            return json.load(f)
    return {}


def _extract_metrics(report: dict) -> dict:
    """Extract key metrics from anomaly report."""
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
    args = parser.parse_args()

    # Generate patterns
    keys = sorted(_SEARCH_GRID.keys())
    values = [_SEARCH_GRID[k] for k in keys]
    all_patterns = []
    for combo in itertools.product(*values):
        w = dict(_DEFAULTS)
        for k, v in zip(keys, combo):
            w[k] = v
        all_patterns.append(w)

    if args.patterns > 0:
        all_patterns = all_patterns[:args.patterns]

    print(f"Weight search: {len(all_patterns)} patterns x {args.games} games\n")

    results = []
    start_game = 4000

    for i, pattern in enumerate(all_patterns):
        label = " | ".join(f"{k}={pattern[k]}" for k in keys)
        print(f"[{i+1}/{len(all_patterns)}] {label}")

        _write_weights(pattern)

        ok = _run_simulation(args.games, start_game)
        if not ok:
            print(f"  FAILED — skipping")
            start_game += args.games
            continue

        prefix = f"g{start_game:04d}"
        out_dir = os.path.join(args.output, f"weight_search_{i:02d}")
        os.makedirs(out_dir, exist_ok=True)
        report = _run_anomaly_detection(prefix, out_dir)
        metrics = _extract_metrics(report)

        result = {
            "pattern_id": i,
            "weights": {k: pattern[k] for k in keys},
            "metrics": metrics,
        }
        results.append(result)
        games = metrics.get("games", 0)
        anomalies = metrics.get("anomalies_total", 0)
        per_game = anomalies / games if games else 0
        print(f"  {games}g | anomalies={anomalies} ({per_game:.2f}/g) | "
              f"safety: atk={metrics.get('attack_available_but_no_attack',0)} "
              f"end={metrics.get('end_when_attack_available',0)} "
              f"ret={metrics.get('retreat_when_attack_available',0)}")

        start_game += args.games

    # Restore defaults
    _restore_defaults()
    print(f"\nDefaults restored.")

    # Save results
    os.makedirs(args.output, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.output, f"level6_weight_search_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "schema_version": "1.0",
            "search_grid": _SEARCH_GRID,
            "defaults": _DEFAULTS,
            "games_per_pattern": args.games,
            "results": results,
        }, f, indent=2)

    # Also write baseline report
    baseline_path = os.path.join(args.output, "level6_weight_search_baseline.json")
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump({
            "schema_version": "1.0",
            "search_grid": _SEARCH_GRID,
            "defaults": _DEFAULTS,
            "games_per_pattern": args.games,
            "patterns_tested": len(results),
            "results": results,
        }, f, indent=2)

    print(f"\nResults saved: {out_path}")
    print(f"Baseline: {baseline_path}")

    # Summary
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
