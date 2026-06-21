"""
Semi-automated weight tuning runner.

Combines auto_tune (planning), weight_search (execution),
promotion_gate (decision), and search_history (tracking) into
a single command.

Usage:
  # Dry-run (plan only, no games):
  python tools/auto_tune_runner.py --parameter advantage_weight --stage 30g \\
      --games 30 --start-game 11000 --output reports --dry-run

  # Execute games:
  python tools/auto_tune_runner.py --parameter advantage_weight --stage 30g \\
      --games 30 --start-game 11000 --use-wsl --output reports --run

  # Execute + update search history:
  python tools/auto_tune_runner.py --parameter advantage_weight --stage 30g \\
      --games 30 --start-game 11000 --use-wsl --output reports --run --update-history
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

from tools.search_history import load as load_history, should_skip, add_entry, save as save_history
from tools.promotion_gate import evaluate_stage

_SEARCH_GRID = {
    "advantage_weight": [0.2, 0.3, 0.4, 0.5, 0.6],
    "energy_to_plan_bonus": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
    "energy_to_plan_bonus_no_need": [1.0, 2.0, 3.0, 4.0],
    "voltorb_ko_attack_bonus": [500.0, 750.0, 1000.0, 1250.0, 1500.0],
    "voltorb_damage_scaling": [0.4, 0.6, 0.8, 1.0, 1.2],
    "energy_attack_enablement_bonus": [150.0, 200.0, 300.0, 400.0, 500.0],
    "evolve_first_bellibolt_bonus": [110.0, 165.0, 220.0, 275.0, 330.0],
}

_EXCLUDED_PARAMETERS = {
    "retreat_to_better_attacker_bonus",
    "attack_suppress_penalty",
}

_VALID_STAGES = {"30g", "50g", "200g"}

_SAFETY_KEYS = [
    "attack_available_but_no_attack",
    "end_when_attack_available",
    "retreat_when_attack_available",
]

_WEIGHTS_PATH = os.path.join(_REPO_ROOT, "data", "weights.json")
_HISTORY_PATH = os.path.join(_REPO_ROOT, "reports", "search_history.json")


def _load_weights(path: str = _WEIGHTS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _check_safety(metrics: dict) -> str:
    for k in _SAFETY_KEYS:
        if metrics.get(k, 0) > 0:
            return f"{k}={metrics[k]}"
    return "all_0"


def plan(parameter: str, stage: str, history_path: str = _HISTORY_PATH,
         weights_path: str = _WEIGHTS_PATH) -> dict:
    """Generate a plan for the given parameter.

    Returns dict with keys: parameter, stage, baseline_value, candidates,
    skipped, runnable, error (if any).
    """
    if parameter in _EXCLUDED_PARAMETERS:
        return {"error": f"Parameter '{parameter}' is excluded from search."}
    if parameter not in _SEARCH_GRID:
        return {"error": f"Unknown parameter '{parameter}'. Valid: {sorted(_SEARCH_GRID.keys())}"}
    if stage not in _VALID_STAGES:
        return {"error": f"Invalid stage '{stage}'. Valid: {sorted(_VALID_STAGES)}"}

    weights = _load_weights(weights_path)
    baseline_value = weights.get(parameter)
    history = load_history(history_path)
    values = _SEARCH_GRID[parameter]

    skipped = []
    runnable = []
    for val in values:
        if val == baseline_value:
            skipped.append({"value": val, "reason": "current baseline"})
            continue
        skip, reason = should_skip(history, parameter, val)
        if skip:
            skipped.append({"value": val, "reason": reason})
        else:
            runnable.append(val)

    return {
        "parameter": parameter,
        "stage": stage,
        "baseline_value": baseline_value,
        "candidates": values,
        "skipped": skipped,
        "runnable": runnable,
    }


def build_grid(parameter: str, baseline_value, values: list) -> dict:
    """Build grid with baseline as first pattern, then candidates."""
    patterns = [{parameter: baseline_value}]
    patterns.extend({parameter: v} for v in values)
    return {
        "description": f"Auto-tune runner: {parameter} search (pattern 0 = baseline)",
        "patterns": patterns,
    }


def build_command(grid_path: str, games: int, start_game: int,
                  output: str, use_wsl: bool) -> list:
    cmd = [
        sys.executable, "experiments/weight_search.py",
        "--grid-file", grid_path,
        "--games", str(games),
        "--start-game", str(start_game),
        "--output", output,
    ]
    if use_wsl:
        cmd.append("--use-wsl")
    return cmd


def parse_results(output_dir: str, parameter: str, num_patterns: int) -> list:
    """Parse weight_search output directories for metrics."""
    results = []
    for i in range(num_patterns):
        rpt_dir = os.path.join(_REPO_ROOT, output_dir, f"weight_search_{i:02d}")
        rpt_path = os.path.join(rpt_dir, "latest_anomaly_report.json")
        if not os.path.exists(rpt_path):
            results.append(None)
            continue
        with open(rpt_path) as f:
            rpt = json.load(f)
        s = rpt.get("summary", {})
        results.append({
            "games": s.get("games", 0),
            "anomalies_total": s.get("anomalies_total", 0),
            "anomalies_per_game": round(s.get("anomalies_total", 0) / max(s.get("games", 1), 1), 2),
            "attack_available_but_no_attack": s.get("attack_available_but_no_attack", 0),
            "end_when_attack_available": s.get("end_when_attack_available", 0),
            "retreat_when_attack_available": s.get("retreat_when_attack_available", 0),
        })
    return results


def evaluate_results(
    parameter: str, stage: str, baseline_apg: float,
    runnable: list, metrics_list: list,
) -> list:
    """Run promotion gate on each candidate."""
    decisions = []
    for val, m in zip(runnable, metrics_list):
        if m is None:
            decisions.append({
                "value": val, "anomalies_per_game": None,
                "decision": "error", "promote": False,
                "reason": "No results found", "safety": "unknown",
            })
            continue
        safety = _check_safety(m)
        r = evaluate_stage(stage, baseline_apg, m["anomalies_per_game"], safety)
        decisions.append({
            "value": val,
            "anomalies_per_game": m["anomalies_per_game"],
            "delta": r["delta"],
            "vs_baseline_pct": r["improvement_percent"],
            "safety": safety,
            "decision": r["decision"],
            "promote": r["promote"],
            "next_action": r.get("next_action", ""),
        })
    return decisions


def build_summary(
    parameter: str, stage: str, games: int, start_game: int,
    baseline_value, baseline_apg: float,
    skipped: list, decisions: list,
    history_updated: bool, weights_restored: bool,
) -> dict:
    promoted = [d for d in decisions if d.get("promote")]
    return {
        "schema_version": "1.0",
        "parameter": parameter,
        "stage": stage,
        "games": games,
        "start_game": start_game,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "baseline_value": baseline_value,
        "baseline_anomalies_per_game": baseline_apg,
        "candidates": decisions,
        "promoted_candidates": [d["value"] for d in promoted],
        "skipped_candidates": skipped,
        "search_history_updated": history_updated,
        "weights_restored": weights_restored,
        "next_recommended_action": (
            f"Run 50g validation for {promoted[0]['value']}" if promoted and stage == "30g"
            else f"Run 200g confirmation for {promoted[0]['value']}" if promoted and stage == "50g"
            else "Create adoption PR" if promoted and stage == "200g"
            else f"No candidates promoted. {parameter} confirmed at {baseline_value}."
        ),
    }


def format_summary_md(summary: dict) -> str:
    lines = [f"# Auto-Tune Runner: {summary['parameter']} {summary['stage']}", ""]

    lines.append("## Setup")
    lines.append("")
    lines.append(f"- Parameter: **{summary['parameter']}**")
    lines.append(f"- Stage: **{summary['stage']}**")
    lines.append(f"- Games: {summary['games']}")
    lines.append(f"- Baseline: {summary['parameter']}=**{summary['baseline_value']}**")
    lines.append(f"- Baseline anomalies/g: **{summary['baseline_anomalies_per_game']}**")
    lines.append("")

    if summary["skipped_candidates"]:
        lines.append("## Skipped Candidates")
        lines.append("")
        lines.append("| Value | Reason |")
        lines.append("|-------|--------|")
        for s in summary["skipped_candidates"]:
            lines.append(f"| {s['value']} | {s['reason']} |")
        lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append("| Value | /game | Delta | vs Baseline | Safety | Decision |")
    lines.append("|-------|-------|-------|-------------|--------|----------|")
    for d in summary["candidates"]:
        apg = d.get("anomalies_per_game", "-")
        delta = f"{d['delta']:+.4f}" if d.get("delta") is not None else "-"
        pct = f"{d['vs_baseline_pct']:+.2f}%" if d.get("vs_baseline_pct") is not None else "-"
        lines.append(f"| {d['value']} | {apg} | {delta} | {pct} | {d['safety']} | {d['decision']} |")
    lines.append("")

    lines.append("## Promotion")
    lines.append("")
    if summary["promoted_candidates"]:
        lines.append(f"Promoted: {summary['promoted_candidates']}")
    else:
        lines.append("No candidates promoted.")
    lines.append("")

    lines.append(f"## Next Action")
    lines.append("")
    lines.append(summary["next_recommended_action"])
    lines.append("")

    lines.append("## Safety")
    lines.append("")
    lines.append(f"- weights.json restored: {summary['weights_restored']}")
    lines.append(f"- search_history updated: {summary['search_history_updated']}")
    lines.append("- Adoption: not yet (human review required)")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Semi-automated weight tuning runner")
    parser.add_argument("--parameter", required=True, help="Weight parameter to tune")
    parser.add_argument("--stage", default="30g", choices=sorted(_VALID_STAGES))
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--start-game", type=int, default=11000)
    parser.add_argument("--output", default="reports")
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--history", default=_HISTORY_PATH)
    parser.add_argument("--weights", default=_WEIGHTS_PATH)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan only, do not run games")
    mode.add_argument("--run", action="store_true", help="Execute weight search")

    parser.add_argument("--update-history", action="store_true",
                        help="Update search_history.json with results")

    args = parser.parse_args()

    p = plan(args.parameter, args.stage, args.history, args.weights)
    if "error" in p:
        print(f"Error: {p['error']}")
        sys.exit(1)

    prefix = f"auto_tune_runner_{args.parameter}_{args.stage}"

    print(f"Parameter: {args.parameter}")
    print(f"Stage: {args.stage}")
    print(f"Baseline: {args.parameter}={p['baseline_value']}")
    print(f"Runnable: {p['runnable']}")
    print(f"Skipped: {[s['value'] for s in p['skipped']]}")

    if not p["runnable"]:
        print("\nNo runnable candidates. Nothing to do.")
        summary = build_summary(
            args.parameter, args.stage, args.games, args.start_game,
            p["baseline_value"], 0.0, p["skipped"], [], False, True,
        )
        _save_outputs(args.output, prefix, summary)
        return

    grid = build_grid(args.parameter, p["baseline_value"], p["runnable"])
    grid_path = os.path.join(_REPO_ROOT, args.output, f"{prefix}_grid.json")
    os.makedirs(os.path.dirname(grid_path), exist_ok=True)
    with open(grid_path, "w", encoding="utf-8") as f:
        json.dump(grid, f, indent=2)
        f.write("\n")
    print(f"\nGrid file: {grid_path}")
    print(f"  Pattern 0 = baseline ({p['baseline_value']})")
    print(f"  Patterns 1-{len(p['runnable'])} = candidates")

    cmd = build_command(
        os.path.relpath(grid_path, _REPO_ROOT),
        args.games, args.start_game, args.output, args.use_wsl,
    )
    print(f"Command: {' '.join(cmd)}")

    if args.dry_run:
        print("\n[DRY-RUN] Would execute the above command.")
        print("[DRY-RUN] No games run. No results to evaluate.")
        return

    print(f"\nRunning weight search...")
    # Grid has baseline + N candidates = N+1 total patterns
    result = subprocess.run(cmd, cwd=_REPO_ROOT, timeout=1200)
    if result.returncode != 0:
        print("Weight search failed.")
        sys.exit(1)

    weights_after = _load_weights(args.weights)
    weights_restored = weights_after.get(args.parameter) == p["baseline_value"]
    print(f"\nweights.json {args.parameter}={weights_after.get(args.parameter)} "
          f"(restored={weights_restored})")

    # Pattern 0 = baseline, patterns 1..N = candidates
    total_patterns = 1 + len(p["runnable"])
    all_metrics = parse_results(args.output, args.parameter, total_patterns)

    baseline_metrics = all_metrics[0]
    candidate_metrics = all_metrics[1:]

    baseline_apg = baseline_metrics["anomalies_per_game"] if baseline_metrics else 0.0
    print(f"Baseline result: {baseline_apg}/g")

    decisions = evaluate_results(
        args.parameter, args.stage, baseline_apg, p["runnable"], candidate_metrics,
    )

    history_updated = False
    if args.update_history:
        history = load_history(args.history)
        for d in decisions:
            if d.get("anomalies_per_game") is not None:
                add_entry(
                    history, args.parameter, d["value"],
                    "hold" if d["decision"] in ("promote", "no_promote") else d["decision"],
                    args.stage, d["anomalies_per_game"], d["safety"],
                    d.get("next_action", ""),
                )
        save_history(history, args.history)
        history_updated = True
        print(f"search_history.json updated.")

    summary = build_summary(
        args.parameter, args.stage, args.games, args.start_game,
        p["baseline_value"], baseline_apg,
        p["skipped"], decisions, history_updated, weights_restored,
    )

    _save_outputs(args.output, prefix, summary)


def _save_outputs(output_dir: str, prefix: str, summary: dict):
    base = os.path.join(_REPO_ROOT, output_dir)
    os.makedirs(base, exist_ok=True)

    json_path = os.path.join(base, f"{prefix}_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Saved: {json_path}")

    md_path = os.path.join(base, f"{prefix}_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(format_summary_md(summary))
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    main()
