"""
Adoption flow: generates adoption plan and post-adoption checklist.

Usage:
  python tools/adoption_flow.py --parameter legal_attack_score \
      --baseline 150.0 --accepted 250.0 \
      --source-pr "#72/#73/#74" --consistency "30g=-9.4%,50g=-16.6%,200g=-7.4%"

  python tools/adoption_flow.py --parameter legal_attack_score \
      --baseline 150.0 --accepted 250.0 \
      --source-pr "#72/#73/#74" --consistency "30g=-9.4%,50g=-16.6%,200g=-7.4%" \
      --apply
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_WEIGHTS_PATH = os.path.join(_REPO_ROOT, "data", "weights.json")


def generate_adoption_plan(
    parameter: str, baseline: float, accepted: float,
    source_pr: str = "", consistency: str = "",
) -> dict:
    return {
        "schema_version": "1.0",
        "parameter": parameter,
        "baseline_value": baseline,
        "adopted_value": accepted,
        "consistency": consistency,
        "safety": "all_0",
        "source_pr": source_pr,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "changes": [
            {"file": "data/weights.json", "field": parameter,
             "from": baseline, "to": accepted},
        ],
        "post_adoption_checklist": [
            {"step": 1, "action": "Update data/weights.json", "auto": True},
            {"step": 2, "action": "Run tests", "auto": True},
            {"step": 3, "action": "Smoke check (30g)", "auto": False},
            {"step": 4, "action": "Create adoption PR", "auto": False},
            {"step": 5, "action": "Merge adoption PR", "auto": False},
            {"step": 6, "action": "Rebuild submission.tar.gz", "auto": True},
            {"step": 7, "action": "Create submission update PR", "auto": False},
            {"step": 8, "action": "Tag stable version", "auto": False},
        ],
    }


def apply_adoption(parameter: str, accepted: float,
                   weights_path: str = _WEIGHTS_PATH) -> bool:
    """Update weights.json with the accepted value. Returns True on success."""
    with open(weights_path, encoding="utf-8") as f:
        data = json.load(f)
    old = data.get(parameter)
    data[parameter] = accepted
    with open(weights_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  {parameter}: {old} -> {accepted}")
    return True


def format_plan_md(plan: dict) -> str:
    lines = [f"# Adoption Plan: {plan['parameter']}={plan['adopted_value']}", ""]
    lines.append(f"- Parameter: **{plan['parameter']}**")
    lines.append(f"- Previous: {plan['baseline_value']}")
    lines.append(f"- Adopted: **{plan['adopted_value']}**")
    lines.append(f"- Source: {plan.get('source_pr', 'N/A')}")
    lines.append(f"- Safety: {plan['safety']}")
    if plan.get("consistency"):
        lines.append(f"- Consistency: {plan['consistency']}")
    lines.append("")
    lines.append("## Checklist")
    lines.append("")
    for item in plan["post_adoption_checklist"]:
        auto = "(auto)" if item["auto"] else "(manual)"
        lines.append(f"- [ ] Step {item['step']}: {item['action']} {auto}")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Adoption flow")
    parser.add_argument("--parameter", required=True)
    parser.add_argument("--baseline", type=float, required=True)
    parser.add_argument("--accepted", type=float, required=True)
    parser.add_argument("--source-pr", default="")
    parser.add_argument("--consistency", default="")
    parser.add_argument("--output", default="reports")
    parser.add_argument("--apply", action="store_true",
                        help="Apply the value change to data/weights.json")

    args = parser.parse_args()

    plan = generate_adoption_plan(
        args.parameter, args.baseline, args.accepted,
        args.source_pr, args.consistency,
    )

    base = os.path.join(_REPO_ROOT, args.output)
    os.makedirs(base, exist_ok=True)

    prefix = f"{args.parameter}_adoption"
    json_path = os.path.join(base, f"{prefix}_plan.json")
    md_path = os.path.join(base, f"{prefix}_plan.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(format_plan_md(plan))

    print(f"Adoption plan: {json_path}")
    print(f"Checklist: {md_path}")

    if args.apply:
        print("\nApplying adoption...")
        apply_adoption(args.parameter, args.accepted)
        print("Done. Run tests to verify.")
    else:
        print("\n[DRY-RUN] Use --apply to update data/weights.json.")


if __name__ == "__main__":
    main()
