"""
Auto-tune pipeline MVP.

Runs a single parameter through one stage of validation (30g/50g/200g),
generates reports, and records results in search_history.

Usage:
  python tools/auto_tune_pipeline.py \
      --parameter evolve_first_bellibolt_bonus \
      --stage 50g --baseline 220.0 --candidates 330.0 \
      --games 50 --start-game 20200 --use-wsl

  python tools/auto_tune_pipeline.py \
      --parameter energy_attack_enablement_bonus \
      --stage 30g --baseline 300.0 --candidates 150,200,400,500 \
      --games 30 --start-game 16000 --use-wsl
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

from tools.promotion_gate import evaluate_stage
from tools.search_history import load as load_history, add_entry, save as save_history

_WEIGHTS_PATH = os.path.join(_REPO_ROOT, "data", "weights.json")
_HISTORY_PATH = os.path.join(_REPO_ROOT, "reports", "search_history.json")
_VALID_STAGES = {"30g", "50g", "200g"}


def _load_weights(path: str = _WEIGHTS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_grid(parameter: str, baseline: float, candidates: list[float]) -> dict:
    patterns = [{ parameter: baseline }]
    patterns.extend({ parameter: c } for c in candidates)
    return {
        "description": f"auto_tune_pipeline: {parameter} (pattern 0 = baseline)",
        "patterns": patterns,
    }


def _run_search(grid_path: str, games: int, start_game: int,
                output: str, use_wsl: bool) -> int:
    cmd = [
        sys.executable, "experiments/weight_search.py",
        "--grid-file", grid_path,
        "--games", str(games),
        "--start-game", str(start_game),
        "--output", output,
    ]
    if use_wsl:
        cmd.append("--use-wsl")
    r = subprocess.run(cmd, cwd=_REPO_ROOT, timeout=1200)
    return r.returncode


def _parse_pattern_result(output_dir: str, pattern_idx: int) -> dict | None:
    rpt_path = os.path.join(
        _REPO_ROOT, output_dir, f"weight_search_{pattern_idx:02d}",
        "latest_anomaly_report.json"
    )
    if not os.path.exists(rpt_path):
        return None
    with open(rpt_path) as f:
        rpt = json.load(f)
    s = rpt.get("summary", {})
    g = max(s.get("games", 1), 1)
    return {
        "games": s.get("games", 0),
        "anomalies_total": s.get("anomalies_total", 0),
        "anomalies_per_game": round(s.get("anomalies_total", 0) / g, 2),
        "attack_available_but_no_attack": s.get("attack_available_but_no_attack", 0),
        "end_when_attack_available": s.get("end_when_attack_available", 0),
        "retreat_when_attack_available": s.get("retreat_when_attack_available", 0),
    }


def _check_safety(m: dict) -> str:
    for k in ["attack_available_but_no_attack", "end_when_attack_available",
              "retreat_when_attack_available"]:
        if m.get(k, 0) > 0:
            return f"{k}={m[k]}"
    return "all_0"


def run_pipeline(
    parameter: str, stage: str, baseline: float, candidates: list[float],
    games: int, start_game: int, output: str, use_wsl: bool,
    update_history: bool = True,
) -> dict:
    """Run one stage of the tuning pipeline. Returns summary dict."""
    prefix = f"{parameter}_{stage}"

    grid = _build_grid(parameter, baseline, candidates)
    grid_path = os.path.join(_REPO_ROOT, output, f"{prefix}_grid.json")
    os.makedirs(os.path.dirname(grid_path), exist_ok=True)
    with open(grid_path, "w", encoding="utf-8") as f:
        json.dump(grid, f, indent=2)
        f.write("\n")

    print(f"Pipeline: {parameter} {stage}")
    print(f"  Baseline: {baseline}")
    print(f"  Candidates: {candidates}")
    print(f"  Games: {games}")
    print(f"  Grid: {grid_path}")

    rc = _run_search(
        os.path.relpath(grid_path, _REPO_ROOT),
        games, start_game, output, use_wsl,
    )
    if rc != 0:
        return {"error": f"weight_search failed with exit code {rc}"}

    weights_after = _load_weights()
    weights_restored = weights_after.get(parameter) == baseline
    print(f"\n  weights.json restored: {weights_restored}")

    total_patterns = 1 + len(candidates)
    baseline_m = _parse_pattern_result(output, 0)
    candidate_results = [_parse_pattern_result(output, i + 1) for i in range(len(candidates))]

    if not baseline_m:
        return {"error": "Baseline result not found"}

    baseline_apg = baseline_m["anomalies_per_game"]
    print(f"  Baseline result: {baseline_apg}/g")

    decisions = []
    for val, m in zip(candidates, candidate_results):
        if m is None:
            decisions.append({
                "value": val, "anomalies_per_game": None,
                "decision": "error", "promote": False, "safety": "unknown",
            })
            continue
        safety = _check_safety(m)
        pct = round((m["anomalies_per_game"] - baseline_apg) / baseline_apg * 100, 2) if baseline_apg > 0 else 0
        r = evaluate_stage(stage, baseline_apg, m["anomalies_per_game"], safety)

        dec = r["decision"]
        prom = r["promote"]
        if stage == "30g" and prom and abs(pct) < 5.0:
            dec = "hold"
            prom = False

        decisions.append({
            "value": val,
            "anomalies_per_game": m["anomalies_per_game"],
            "delta": round(m["anomalies_per_game"] - baseline_apg, 4),
            "vs_baseline_pct": pct,
            "safety": safety,
            "decision": dec,
            "promote": prom,
        })
        print(f"  {val}: {m['anomalies_per_game']}/g ({pct:+.1f}%) -> {dec}")

    promoted = [d for d in decisions if d["promote"]]
    next_stage = {"30g": "50g", "50g": "200g", "200g": "adoption"}.get(stage, "done")

    summary = {
        "schema_version": "1.0",
        "parameter": parameter,
        "stage": stage,
        "games": games,
        "start_game": start_game,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "baseline_value": baseline,
        "baseline_anomalies_per_game": baseline_apg,
        "candidates": decisions,
        "promoted": [d["value"] for d in promoted],
        "weights_restored": weights_restored,
        "next_action": (
            f"Run {next_stage} for {promoted[0]['value']}" if promoted and next_stage != "adoption"
            else f"Create adoption PR for {promoted[0]['value']}" if promoted
            else f"No candidates promoted. {parameter}={baseline} confirmed."
        ),
    }

    summary_json = os.path.join(_REPO_ROOT, output, f"{prefix}_summary.json")
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write("\n")

    summary_md = os.path.join(_REPO_ROOT, output, f"{prefix}_summary.md")
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write(_format_md(summary))

    if update_history:
        h = load_history(_HISTORY_PATH)
        for d in decisions:
            if d.get("anomalies_per_game") is not None:
                result = d["decision"] if d["decision"] in ("promote", "reject") else "hold"
                add_entry(h, parameter, d["value"], result, stage,
                          d["anomalies_per_game"], d["safety"],
                          f"{stage}: {d['vs_baseline_pct']:+.1f}% vs baseline.")
        save_history(h, _HISTORY_PATH)
        print("  search_history.json updated.")

    print(f"\n  Summary: {summary_json}")
    print(f"  Next: {summary['next_action']}")
    return summary


def _format_md(s: dict) -> str:
    lines = [f"# {s['parameter']} {s['stage']} Pipeline Result", ""]
    lines.append(f"- Parameter: **{s['parameter']}**")
    lines.append(f"- Stage: **{s['stage']}**")
    lines.append(f"- Baseline: {s['baseline_value']} ({s['baseline_anomalies_per_game']}/g)")
    lines.append("")
    lines.append("| Value | /game | Delta | vs Baseline | Safety | Decision |")
    lines.append("|-------|-------|-------|-------------|--------|----------|")
    for d in s["candidates"]:
        apg = d.get("anomalies_per_game", "-")
        delta = f"{d['delta']:+.4f}" if d.get("delta") is not None else "-"
        pct = f"{d['vs_baseline_pct']:+.1f}%" if d.get("vs_baseline_pct") is not None else "-"
        lines.append(f"| {d['value']} | {apg} | {delta} | {pct} | {d['safety']} | {d['decision']} |")
    lines.append("")
    lines.append(f"**Next:** {s['next_action']}")
    lines.append(f"\nweights.json restored: {s['weights_restored']}")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Auto-tune pipeline MVP")
    parser.add_argument("--parameter", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(_VALID_STAGES))
    parser.add_argument("--baseline", type=float, required=True)
    parser.add_argument("--candidates", required=True,
                        help="Comma-separated candidate values")
    parser.add_argument("--games", type=int, required=True)
    parser.add_argument("--start-game", type=int, required=True)
    parser.add_argument("--output", default="reports")
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--no-history", action="store_true",
                        help="Do not update search_history.json")

    args = parser.parse_args()
    candidates = [float(v.strip()) for v in args.candidates.split(",")]

    summary = run_pipeline(
        args.parameter, args.stage, args.baseline, candidates,
        args.games, args.start_game, args.output, args.use_wsl,
        update_history=not args.no_history,
    )

    if "error" in summary:
        print(f"Error: {summary['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
