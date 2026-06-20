"""
Level 4: Generate fix candidates and a Claude Code fix prompt from anomaly reports.

Usage:
  python tools/generate_fix_prompt.py --input reports/latest_anomaly_report.json --output reports
  python tools/generate_fix_prompt.py --input reports/latest_anomaly_report.json --output reports --top 20
  python tools/generate_fix_prompt.py --input reports/latest_anomaly_report.json --output reports --deck-profile data/deck_profile.json
  python tools/generate_fix_prompt.py --input reports/latest_anomaly_report.json --output reports --focus voltorb_over_kilowattrel_missed
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tools.classify_anomalies import classify_anomalies, generate_fix_candidates


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def _build_candidates_json(
    candidates: list[dict],
    classification: dict,
    source_report: str,
    deck_profile_id: str,
) -> dict:
    high = sum(1 for c in candidates if c["priority"] == "high")
    med  = sum(1 for c in candidates if c["priority"] == "medium")
    low  = sum(1 for c in candidates if c["priority"] == "low")
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report": source_report,
        "deck_profile_id": deck_profile_id,
        "summary": {
            "anomalies_total": sum(classification["summary"].values()),
            "candidate_total": len(candidates),
            "high_priority_candidates": high,
            "medium_priority_candidates": med,
            "low_priority_candidates": low,
        },
        "classification": classification["summary"],
        "fix_candidates": candidates,
    }


def _build_candidates_md(candidates: list[dict], classification: dict) -> str:
    lines = ["# Fix Candidate Report", ""]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"Generated: {ts}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")
    total = sum(classification["summary"].values())
    lines.append(f"| anomalies_total | {total} |")
    lines.append(f"| fix_candidates | {len(candidates)} |")
    high = sum(1 for c in candidates if c["priority"] == "high")
    med  = sum(1 for c in candidates if c["priority"] == "medium")
    low  = sum(1 for c in candidates if c["priority"] == "low")
    lines.append(f"| high_priority | {high} |")
    lines.append(f"| medium_priority | {med} |")
    lines.append(f"| low_priority | {low} |")
    lines.append("")

    lines.append("## Classification Summary")
    lines.append("")
    lines.append("| Classification | Count | Suggested Action |")
    lines.append("|---|---:|---|")
    for key, cnt in sorted(classification["summary"].items(), key=lambda x: -x[1]):
        action = classification["suggested_actions"].get(key, "")
        lines.append(f"| {key} | {cnt} | {action} |")
    lines.append("")

    fix_cands = [c for c in candidates if not c.get("excluded_from_fix_prompt", False)
                 and c["suggested_change_type"] not in ("no_fix_needed", "no_actionable_fix_game_flow", "logging_improvement")]
    nofix_cands = [c for c in candidates if c.get("excluded_from_fix_prompt", False)
                   or c["suggested_change_type"] in ("no_fix_needed", "no_actionable_fix_game_flow", "logging_improvement", "detector_refinement")]

    if fix_cands:
        lines.append("## Fix Candidates")
        lines.append("")
        for c in fix_cands:
            lines.append(f"### {c['id']}: {c['title']}")
            lines.append(f"- priority: {c['priority']}")
            lines.append(f"- source anomaly: {c['source_anomaly_type']}")
            lines.append(f"- classification: {c['classification']}")
            ev = c["evidence"]
            lines.append(f"- evidence: {ev['count']} cases")
            if ev.get("estimated_voltorb_damage_range"):
                lines.append(f"- voltorb damage range: {ev['estimated_voltorb_damage_range']}")
            lines.append(f"- root cause hypothesis: {c['root_cause_hypothesis']}")
            lines.append(f"- suggested target files: {', '.join(c['suggested_target_files'])}")
            lines.append(f"- risk: {c['risk']}")
            lines.append(f"- requires A/B test: {c['requires_ab_test']}")
            lines.append("")

    nofix_proper = [c for c in nofix_cands if c["suggested_change_type"] == "no_fix_needed"]
    no_actionable = [c for c in nofix_cands if c["suggested_change_type"] == "no_actionable_fix_game_flow"]
    other_nofix = [c for c in nofix_cands if c["suggested_change_type"] not in ("no_fix_needed", "no_actionable_fix_game_flow")]

    if nofix_proper:
        lines.append("## No Fix Needed (correct behavior)")
        lines.append("")
        for c in nofix_proper:
            lines.append(f"- **{c['classification']}**: {c['evidence']['count']} cases — {c['title']}")
        lines.append("")

    if no_actionable:
        lines.append("## No Actionable Fix (game flow constraints)")
        lines.append("")
        for c in no_actionable:
            lines.append(f"- **{c['classification']}**: {c['evidence']['count']} cases — {c['root_cause_hypothesis']}")
        lines.append("")

    if other_nofix:
        lines.append("## Detector Refinement / Logging Improvement")
        lines.append("")
        for c in other_nofix:
            lines.append(f"- **{c['classification']}**: {c['evidence']['count']} cases — {c['suggested_change_type']}")
        lines.append("")

    lines.append("## Next Recommended Action")
    lines.append("")
    if fix_cands:
        top = fix_cands[0]
        lines.append(f"Apply fix candidate **{top['id']}** ({top['classification']}) first.")
        lines.append(f"Run `reports/latest_fix_prompt.md` in Claude Code.")
    else:
        lines.append("No fix candidates generated. Consider refining detectors.")
    lines.append("")
    return "\n".join(lines)


def _build_fix_prompt(candidate: dict) -> str:
    """Build a Claude Code fix prompt for the top candidate."""
    c = candidate
    ev = c["evidence"]
    dmg_info = ""
    if ev.get("estimated_voltorb_damage_range"):
        dmg_info = f"Voltorb estimated damage range: {ev['estimated_voltorb_damage_range']}"

    lines = [
        "# Claude Code Fix Prompt",
        "",
        "**This prompt targets a single fix candidate. Do not apply multiple fixes at once.**",
        "",
        f"## Fix Candidate: {c['id']}",
        "",
        f"## Problem",
        "",
        f"{c['root_cause_hypothesis']}",
        "",
        f"## Evidence",
        "",
        f"- anomaly type: {c['source_anomaly_type']}",
        f"- classification: {c['classification']}",
        f"- occurrence count: {ev['count']}",
        f"- actual attackers: {ev.get('actual_attackers', [])}",
    ]
    if dmg_info:
        lines.append(f"- {dmg_info}")
    lines.extend([
        "",
        "## Suspected Fix Area",
        "",
    ])
    for tf in c["suggested_target_files"]:
        lines.append(f"- {tf}")
    lines.extend([
        "",
        "## Scope",
        "",
        "Allowed changes:",
        "",
    ])
    for tf in c["suggested_target_files"]:
        lines.append(f"- {tf}")
    lines.extend([
        "",
        "## Do Not Change",
        "",
    ])
    for dnc in c.get("do_not_change", ["deck.csv", "submission.tar.gz"]):
        lines.append(f"- {dnc}")
    lines.extend([
        "- Do not apply multiple fix candidates at once",
        "- Do not auto-merge",
        "",
        "## Implementation Guidance",
        "",
    ])

    if c["classification"] == "voltorb_over_kilowattrel_missed":
        lines.extend([
            "When Kilowattrel is active and Voltorb is on bench with enough energy to attack:",
            "- Calculate Voltorb estimated damage (20 + 20 * total Lightning on Iono's Pokemon)",
            "- If Voltorb damage > Kilowattrel 70 AND Voltorb is legally promotable, consider retreat + Voltorb attack",
            "- Only apply when Voltorb is confirmed attack-ready (2+ energy) and retreat is legal",
            "- Preserve Kilowattrel attack when it can KO and Voltorb cannot",
        ])
    elif c["classification"] == "voltorb_over_wattrel_missed":
        lines.extend([
            "Wattrel should not be attacking when Voltorb has significantly higher damage.",
            "- Check if retreat to Voltorb is available",
            "- If Voltorb is attack-ready, strongly prefer retreat + Voltorb attack",
        ])
    elif c["classification"] == "bellibolt_over_voltorb_high_damage":
        lines.extend([
            "When Voltorb estimated damage exceeds 230 (Bellibolt ex fixed damage):",
            "- Consider Voltorb as the better prize-race attacker (non-ex = 1 prize risk vs 2)",
            "- Only apply when Voltorb is confirmed attack-ready and legally promotable",
            "- Preserve Bellibolt attack when only Bellibolt can take a specific KO",
        ])
    else:
        lines.extend([
            f"Investigate and address: {c['title']}",
            "- Check the source anomaly pattern in logs",
            "- Adjust scoring weights or detection logic as appropriate",
        ])

    lines.extend([
        "",
        "## Acceptance Criteria",
        "",
        f"- {c['classification']} count should decrease",
        "- No increase in critical/high anomalies",
        "- No regression in attack rate for any attacker",
        "",
        "## A/B Test Metrics",
        "",
    ])
    for m in c.get("ab_test_metric", []):
        lines.append(f"- {m}")
    lines.extend([
        "",
        "## Verification Commands",
        "",
        "```bash",
        "# 1. Save current report as baseline",
        "cp reports/latest_anomaly_report.json reports/baseline/latest_anomaly_report.json",
        "",
        "# 2. Run simulation (50 games)",
        "python experiments/run_matches_real.py --n 50 --start-game <NEXT_ID>",
        "",
        "# 3. Copy logs to inbox",
        "cp logs/game_g<BATCH>*.jsonl battle_logs/inbox/",
        "",
        "# 4. Run anomaly detection on candidate",
        "python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports/candidate --deck-profile data/deck_profile.json --top 20",
        "",
        "# 5. Compare before/after",
        "python tools/compare_anomaly_reports.py --before reports/baseline/latest_anomaly_report.json --after reports/candidate/latest_anomaly_report.json --output reports",
        "```",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Level 4: Generate fix candidates from anomaly report")
    parser.add_argument("--input", required=True, help="Path to latest_anomaly_report.json")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--deck-profile", default=None, help="Path to deck_profile.json")
    parser.add_argument("--top", type=int, default=20, help="Top N anomalies to consider")
    parser.add_argument("--focus", default=None, help="Focus on a specific classification")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}")
        print("Run Level 3 first: python tools/analyze_battle_logs.py --input battle_logs/inbox --output reports")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        report = json.load(f)

    deck_profile_id = report.get("deck_profile_id", "unknown")
    if args.deck_profile and os.path.exists(args.deck_profile):
        try:
            with open(args.deck_profile, encoding="utf-8") as f:
                dp = json.load(f)
            deck_profile_id = dp.get("deck_id", deck_profile_id)
        except Exception:
            pass

    anomalies = report.get("anomalies", [])
    print(f"Input: {args.input}")
    print(f"  Anomalies: {len(anomalies)}")

    # Classify
    classification = classify_anomalies(anomalies)
    print(f"\n  Classification:")
    for key, cnt in sorted(classification["summary"].items(), key=lambda x: -x[1]):
        action = classification["suggested_actions"].get(key, "")
        print(f"    {key}: {cnt} ({action})")

    # Generate candidates
    candidates = generate_fix_candidates(classification, deck_profile_id)

    # Focus filter
    if args.focus:
        candidates = [c for c in candidates if c["classification"] == args.focus]

    print(f"\n  Fix candidates: {len(candidates)}")
    for c in candidates[:args.top]:
        print(f"    {c['id']} [{c['priority']}] {c['classification']} ({c['evidence']['count']} cases)")

    # Build outputs
    cand_json = _build_candidates_json(candidates, classification, args.input, deck_profile_id)
    cand_md   = _build_candidates_md(candidates, classification)

    # Pick top actionable candidate for fix prompt
    actionable = [c for c in candidates
                  if c["suggested_change_type"] in ("scoring_adjustment", "profile_adjustment")]
    if actionable:
        fix_prompt = _build_fix_prompt(actionable[0])
        prompt_target = actionable[0]["classification"]
    else:
        fix_prompt = "# No Actionable Fix Candidates\n\nAll anomalies are either no-fix or detector-refinement.\n"
        prompt_target = "none"

    # Write outputs
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(os.path.join(args.output, "fix_prompts"), exist_ok=True)

    cj_path = os.path.join(args.output, "latest_fix_candidates.json")
    cm_path = os.path.join(args.output, "latest_fix_candidates.md")
    fp_path = os.path.join(args.output, "latest_fix_prompt.md")

    with open(cj_path, "w", encoding="utf-8") as f:
        json.dump(cand_json, f, indent=2, ensure_ascii=False)
    with open(cm_path, "w", encoding="utf-8") as f:
        f.write(cand_md)
    with open(fp_path, "w", encoding="utf-8") as f:
        f.write(fix_prompt)

    # Dated copies
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fp_dir = os.path.join(args.output, "fix_prompts")
    for src, suffix in [(cj_path, "fix_candidates.json"), (cm_path, "fix_candidates.md"), (fp_path, "fix_prompt.md")]:
        dst = os.path.join(fp_dir, f"{ts}_{suffix}")
        with open(src, "r", encoding="utf-8") as sf:
            content = sf.read()
        with open(dst, "w", encoding="utf-8") as df:
            df.write(content)

    print(f"\nReports written:")
    print(f"  {cj_path}")
    print(f"  {cm_path}")
    print(f"  {fp_path}  (target: {prompt_target})")
    print(f"  {fp_dir}/{ts}_*.{{json,md}}")


if __name__ == "__main__":
    main()
