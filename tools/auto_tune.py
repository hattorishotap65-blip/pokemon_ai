"""
Auto-tune planner for weight tuning.

Generates a plan of candidate weight values to explore, filtering out
already-explored candidates via search_history.json. Does NOT execute
any games — only produces a runnable plan.

Usage:
  python tools/auto_tune.py \
      --weights data/weights.json \
      --history reports/search_history.json \
      --stage 30g \
      --output reports/auto_tune_plan.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tools.search_history import load as load_history, should_skip

_SEARCH_GRID = {
    "advantage_weight": [0.2, 0.3, 0.4, 0.5, 0.6],
    "energy_to_plan_bonus": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
    "energy_to_plan_bonus_no_need": [1.0, 2.0, 3.0, 4.0],
    "voltorb_ko_attack_bonus": [500.0, 750.0, 1000.0, 1250.0, 1500.0],
    "voltorb_damage_scaling": [0.4, 0.6, 0.8, 1.0, 1.2],
    "energy_attack_enablement_bonus": [150.0, 200.0, 300.0, 400.0, 500.0],
    "evolve_first_bellibolt_bonus": [110.0, 165.0, 220.0, 275.0, 330.0],
    "evolve_first_kilowattrel_bonus": [3.5, 5.0, 7.0, 10.0, 14.0],
}

_EXCLUDED_PARAMETERS = {
    "retreat_to_better_attacker_bonus",
    "attack_suppress_penalty",
}

_VALID_STAGES = {"30g", "50g", "200g"}


def generate_plan(
    weights_path: str,
    history_path: str,
    stage: str,
) -> dict:
    if stage not in _VALID_STAGES:
        return {
            "schema_version": "1.0",
            "error": f"Invalid stage: {stage}. Must be one of {sorted(_VALID_STAGES)}.",
        }

    with open(weights_path, encoding="utf-8") as f:
        weights = json.load(f)

    history = load_history(history_path)

    stable_baseline = {}
    for key in list(_SEARCH_GRID.keys()) + list(_EXCLUDED_PARAMETERS):
        if key in weights:
            stable_baseline[key] = weights[key]

    generated = []
    skipped = []
    runnable = []

    for param, values in _SEARCH_GRID.items():
        current = weights.get(param)
        for val in values:
            candidate = {"parameter": param, "value": val}
            if val == current:
                skipped.append({**candidate, "reason": "current baseline value"})
                continue
            skip, reason = should_skip(history, param, val)
            if skip:
                skipped.append({**candidate, "reason": reason})
            else:
                runnable.append(candidate)
            generated.append(candidate)

    grid_patterns = []
    for c in runnable:
        pattern = {k: v for k, v in stable_baseline.items() if k in _SEARCH_GRID}
        pattern[c["parameter"]] = c["value"]
        grid_patterns.append(pattern)

    grid_file_content = {
        "description": f"Auto-generated grid for {stage} search",
        "patterns": grid_patterns,
    }

    cmd = (
        f"python experiments/weight_search.py "
        f"--grid-file reports/auto_tune_grid.json "
        f"--games {stage.replace('g', '')} --use-wsl --start-game 9800"
    )

    return {
        "schema_version": "1.0",
        "stage": stage,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "stable_baseline": stable_baseline,
        "excluded_parameters": sorted(_EXCLUDED_PARAMETERS),
        "candidate_parameters": sorted(_SEARCH_GRID.keys()),
        "generated_candidates": len(generated),
        "skipped_candidates": skipped,
        "runnable_candidates": runnable,
        "grid_file": grid_file_content,
        "recommended_next_command": cmd,
        "notes": [
            "This plan does not execute any games.",
            "Run the recommended command to start 30g evaluation.",
            "After evaluation, use promotion_gate.py to decide promotion.",
            "Human review required before adoption.",
        ],
    }


def format_markdown(plan: dict) -> str:
    if "error" in plan:
        return f"# Auto-Tune Plan\n\nError: {plan['error']}\n"

    lines = ["# Auto-Tune Plan", ""]

    lines.append("## Stable Baseline")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    for k, v in sorted(plan["stable_baseline"].items()):
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## Excluded From Search")
    lines.append("")
    for p in plan["excluded_parameters"]:
        lines.append(f"- {p}")
    lines.append("")

    lines.append("## Candidates")
    lines.append("")
    lines.append(f"- Generated: {plan['generated_candidates']}")
    lines.append(f"- Skipped: {len(plan['skipped_candidates'])}")
    lines.append(f"- Runnable: {len(plan['runnable_candidates'])}")
    lines.append("")

    if plan["skipped_candidates"]:
        lines.append("### Skipped")
        lines.append("")
        lines.append("| Parameter | Value | Reason |")
        lines.append("|-----------|-------|--------|")
        for s in plan["skipped_candidates"]:
            lines.append(f"| {s['parameter']} | {s['value']} | {s['reason']} |")
        lines.append("")

    if plan["runnable_candidates"]:
        lines.append("### Runnable")
        lines.append("")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        for r in plan["runnable_candidates"]:
            lines.append(f"| {r['parameter']} | {r['value']} |")
        lines.append("")

    lines.append("## Next Command")
    lines.append("")
    lines.append(f"```bash\n{plan['recommended_next_command']}\n```")
    lines.append("")

    lines.append("## Human Checkpoints")
    lines.append("")
    for n in plan["notes"]:
        lines.append(f"- {n}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Auto-tune planner for weight tuning")
    parser.add_argument("--weights", default="data/weights.json")
    parser.add_argument("--history", default="reports/search_history.json")
    parser.add_argument("--stage", default="30g", choices=sorted(_VALID_STAGES))
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--markdown", help="Output Markdown path")
    parser.add_argument("--save-grid", help="Save grid file for weight_search.py")

    args = parser.parse_args()
    plan = generate_plan(args.weights, args.history, args.stage)

    if "error" in plan:
        print(f"Error: {plan['error']}")
        sys.exit(1)

    print(format_markdown(plan))

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Saved JSON: {args.output}")

    if args.markdown:
        os.makedirs(os.path.dirname(args.markdown) or ".", exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(format_markdown(plan))
        print(f"Saved Markdown: {args.markdown}")

    if args.save_grid:
        os.makedirs(os.path.dirname(args.save_grid) or ".", exist_ok=True)
        with open(args.save_grid, "w", encoding="utf-8") as f:
            json.dump(plan["grid_file"], f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Saved grid: {args.save_grid}")


if __name__ == "__main__":
    main()
