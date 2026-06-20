"""
Level 7: Prepare PR candidate from evaluation result.

Reads the output of evaluate_candidate.py and, if decision == "accept",
generates a PR-ready summary in Markdown and JSON.

Usage:
  python tools/prepare_pr_candidate.py \
    --input reports/level7_candidate_evaluation.json \
    --output reports
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def _infer_changed_files(candidate: str) -> list[str]:
    """Best-effort inference of files that would change for this candidate."""
    c = candidate.lower()
    files = []
    if "weight" in c or "bonus" in c or "penalty" in c or "retreat" in c:
        files.append("data/weights.json")
        files.append("submission.tar.gz")
    if "ionos" in c or "rule" in c or "attack" in c or "pivot" in c:
        files.append("agent/ionos_rules.py")
        files.append("submission.tar.gz")
    if "policy" in c or "score" in c:
        files.append("agent/policy.py")
        files.append("submission.tar.gz")
    return sorted(set(files)) if files else []


def prepare(evaluation: dict) -> dict:
    """Prepare PR candidate from evaluation result."""
    decision = evaluation.get("decision", "unknown")
    candidate = evaluation.get("candidate", "unknown")

    if decision != "accept":
        return {
            "eligible_for_pr": False,
            "candidate": candidate,
            "decision": decision,
            "reason": "Candidate is not eligible for PR creation.",
            "reasons": evaluation.get("reasons", []),
            "next_action": evaluation.get("next_action", ""),
        }

    improved = evaluation.get("improved_metrics", [])
    worsened = evaluation.get("worsened_metrics", [])
    safe_m = evaluation.get("safe_metrics", [])
    missing = evaluation.get("missing_metrics", [])
    reasons = evaluation.get("reasons", [])
    next_action = evaluation.get("next_action", "")
    games_before = evaluation.get("games_before", 0)
    games_after = evaluation.get("games_after", 0)

    # Safety gate: reject if any safety metric is missing
    _SAFETY_REQUIRED = {
        "attack_available_but_no_attack",
        "end_when_attack_available",
        "retreat_when_attack_available",
        "ability_without_followup_attack",
    }
    missing_safety = _SAFETY_REQUIRED & set(missing)
    if missing_safety:
        return {
            "eligible_for_pr": False,
            "candidate": candidate,
            "decision": "accept",
            "reason": f"Safety metrics missing: {sorted(missing_safety)}. Cannot confirm safety.",
            "reasons": reasons,
            "next_action": "Re-run evaluation with safety metrics available.",
        }

    # Build PR summary
    imp_lines = []
    for m in improved:
        imp_lines.append(f"| {m['metric']} | {m['before']} | {m['after']} | {m['delta']:+.4f} |")
    wor_lines = []
    for m in worsened:
        wor_lines.append(f"| {m['metric']} | {m['before']} | {m['after']} | {m['delta']:+.4f} |")

    summary_parts = [
        f"## Candidate: {candidate}",
        "",
        f"Decision: **accept**",
        f"Games: {games_before} (baseline) / {games_after} (candidate)",
        "",
    ]
    if imp_lines:
        summary_parts.append("### Improved")
        summary_parts.append("")
        summary_parts.append("| Metric | Before | After | Delta |")
        summary_parts.append("|--------|--------|-------|-------|")
        summary_parts.extend(imp_lines)
        summary_parts.append("")
    if wor_lines:
        summary_parts.append("### Side Effects (minor)")
        summary_parts.append("")
        summary_parts.append("| Metric | Before | After | Delta |")
        summary_parts.append("|--------|--------|-------|-------|")
        summary_parts.extend(wor_lines)
        summary_parts.append("")

    summary_parts.append("### Safety")
    summary_parts.append("")
    _SAFETY_NAMES = {"attack_available_but_no_attack", "end_when_attack_available",
                     "retreat_when_attack_available", "ability_without_followup_attack"}
    all_m = safe_m + improved + worsened
    safety_entries = [m for m in all_m if m.get("metric") in _SAFETY_NAMES]
    safety_ok = all(m.get("after", 0) == 0 for m in safety_entries) if safety_entries else False
    summary_parts.append(f"All safety metrics: **{'OK' if safety_ok else 'CHECK NEEDED'}**")
    summary_parts.append("")

    suggested_files = _infer_changed_files(candidate)

    return {
        "eligible_for_pr": True,
        "candidate": candidate,
        "decision": "accept",
        "games_before": games_before,
        "games_after": games_after,
        "summary_for_pr": "\n".join(summary_parts),
        "improved_metrics": improved,
        "worsened_metrics": worsened,
        "safe_metrics": safe_m,
        "missing_metrics": missing,
        "reasons": reasons,
        "next_action": next_action,
        "suggested_changed_files": suggested_files,
    }


def generate_markdown(result: dict) -> str:
    lines = ["# PR Candidate Report", ""]
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    if not result.get("eligible_for_pr"):
        lines.append(f"## Candidate: {result['candidate']}")
        lines.append("")
        lines.append(f"**Not eligible for PR.** Decision: {result['decision']}")
        lines.append("")
        lines.append(f"Reason: {result.get('reason', '')}")
        lines.append("")
        if result.get("reasons"):
            lines.append("### Evaluation Reasons")
            lines.append("")
            for r in result["reasons"]:
                lines.append(f"- {r}")
            lines.append("")
        lines.append(f"Next action: {result.get('next_action', 'None')}")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## Eligible for PR: YES")
    lines.append("")
    lines.append(result.get("summary_for_pr", ""))
    lines.append("")

    if result.get("suggested_changed_files"):
        lines.append("### Suggested Changed Files")
        lines.append("")
        for f in result["suggested_changed_files"]:
            lines.append(f"- {f}")
        lines.append("")

    if result.get("reasons"):
        lines.append("### Evaluation Reasons")
        lines.append("")
        for r in result["reasons"]:
            lines.append(f"- {r}")
        lines.append("")

    lines.append(f"### Next Action")
    lines.append("")
    lines.append(result.get("next_action", ""))
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Level 7: Prepare PR candidate")
    parser.add_argument("--input", required=True, help="Path to level7_candidate_evaluation.json")
    parser.add_argument("--output", default="reports", help="Output directory")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: --input not found: {args.input}")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        evaluation = json.load(f)

    result = prepare(evaluation)
    md = generate_markdown(result)

    os.makedirs(args.output, exist_ok=True)
    json_path = os.path.join(args.output, "level7_pr_candidate.json")
    md_path = os.path.join(args.output, "level7_pr_candidate.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    eligible = result.get("eligible_for_pr", False)
    print(f"Candidate: {result['candidate']}")
    print(f"Eligible:  {eligible}")
    print(f"Decision:  {result['decision']}")
    if eligible:
        print(f"Files:     {result.get('suggested_changed_files', [])}")
    print(f"\nReports: {json_path}, {md_path}")


if __name__ == "__main__":
    main()
