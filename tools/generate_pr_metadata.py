"""
Level 7: Generate GitHub PR metadata from PR candidate report.

Reads prepare_pr_candidate.py output and generates title, body,
branch name, and safety notes for a GitHub PR.

Does NOT call GitHub API or create branches/commits.

Usage:
  python tools/generate_pr_metadata.py \
    --input reports/level7_pr_candidate.json \
    --output reports
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert text to a safe branch-name slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s[:max_len].rstrip("-")


def _generate_title(candidate: str) -> str:
    """Generate a short PR title from candidate name."""
    c = candidate.strip()
    if not c or c == "unknown":
        return "feat: adopt accepted candidate"
    slug = re.sub(r"[_=]", " ", c)
    return f"feat: adopt {slug}"


def _generate_branch(candidate: str) -> str:
    """Generate a safe branch name with timestamp to avoid collisions."""
    slug = _slugify(re.sub(r"[_=]", " ", candidate), max_len=30)
    if not slug:
        slug = "accepted-candidate"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return f"feat/adopt-{slug}-{ts}"


def _generate_body(pr_candidate: dict) -> str:
    """Generate full PR body markdown."""
    candidate = pr_candidate.get("candidate", "unknown")
    improved = pr_candidate.get("improved_metrics", [])
    worsened = pr_candidate.get("worsened_metrics", [])
    missing = pr_candidate.get("missing_metrics", [])
    reasons = pr_candidate.get("reasons", [])
    next_action = pr_candidate.get("next_action", "")
    games_before = pr_candidate.get("games_before", 0)
    games_after = pr_candidate.get("games_after", 0)
    files = pr_candidate.get("suggested_changed_files", [])

    lines = [
        "## Summary",
        "",
        f"Adopt **{candidate}** based on A/B validation.",
        "",
        f"## Validation",
        "",
        f"- Games: {games_before} (baseline) / {games_after} (candidate)",
        f"- Decision: **accept**",
        "",
    ]

    if improved:
        lines.append("## Improved Metrics")
        lines.append("")
        lines.append("| Metric | Before | After | Delta |")
        lines.append("|--------|--------|-------|-------|")
        for m in improved:
            lines.append(f"| {m['metric']} | {m['before']} | {m['after']} | {m['delta']:+.4f} |")
        lines.append("")

    if worsened:
        lines.append("## Side Effects (minor)")
        lines.append("")
        lines.append("| Metric | Before | After | Delta |")
        lines.append("|--------|--------|-------|-------|")
        for m in worsened:
            lines.append(f"| {m['metric']} | {m['before']} | {m['after']} | {m['delta']:+.4f} |")
        lines.append("")

    # Safety: use actual values from metrics
    _SAFETY_NAMES = {
        "attack_available_but_no_attack",
        "end_when_attack_available",
        "retreat_when_attack_available",
        "ability_without_followup_attack",
    }
    all_metrics = improved + worsened + pr_candidate.get("safe_metrics", [])
    safety_entries = [m for m in all_metrics if m.get("metric") in _SAFETY_NAMES]

    lines.append("## Safety")
    lines.append("")
    if safety_entries:
        all_zero = all(m.get("after", 0) == 0 for m in safety_entries)
        if all_zero:
            lines.append("All safety metrics confirmed at 0:")
        else:
            lines.append("**WARNING: Safety metrics may have changed:**")
        for m in safety_entries:
            lines.append(f"- {m['metric']}: {m.get('before', '?')} -> {m.get('after', '?')}")
    else:
        lines.append("**Safety metrics not available in evaluation data.**")
    lines.append("")

    if missing:
        lines.append("## Missing Metrics")
        lines.append("")
        for m in missing:
            lines.append(f"- {m}")
        lines.append("")

    if files:
        lines.append("## Changed Files")
        lines.append("")
        for f in files:
            lines.append(f"- {f}")
        lines.append("")

    if reasons:
        lines.append("## Evaluation Reasons")
        lines.append("")
        for r in reasons:
            lines.append(f"- {r}")
        lines.append("")

    if next_action:
        lines.append("## Next Action")
        lines.append("")
        lines.append(next_action)
        lines.append("")

    lines.extend([
        "## Do Not Change",
        "",
        "- deck.csv: unchanged",
        "- No unnecessary agent logic changes",
        "- submission.tar.gz: update only if data/weights.json changed",
        "- No auto-merge (human review required)",
        "",
    ])

    return "\n".join(lines)


def generate_metadata(pr_candidate: dict) -> dict:
    """Generate PR metadata from PR candidate report."""
    eligible = pr_candidate.get("eligible_for_pr", False)
    candidate = pr_candidate.get("candidate", "unknown")

    if not eligible:
        return {
            "ready_to_create_pr": False,
            "candidate": candidate,
            "reason": pr_candidate.get("reason", "Candidate is not eligible for PR creation."),
        }

    # Safety gate: check that safety metrics are available and all zero
    _SAFETY_NAMES = {
        "attack_available_but_no_attack",
        "end_when_attack_available",
        "retreat_when_attack_available",
        "ability_without_followup_attack",
    }
    all_metrics = (pr_candidate.get("improved_metrics", [])
                   + pr_candidate.get("worsened_metrics", [])
                   + pr_candidate.get("safe_metrics", []))
    safety_found = [m for m in all_metrics if m.get("metric") in _SAFETY_NAMES]
    found_names = {m.get("metric") for m in safety_found}
    missing_safety = _SAFETY_NAMES - found_names
    if missing_safety:
        return {
            "ready_to_create_pr": False,
            "candidate": candidate,
            "reason": f"Required safety metrics missing: {sorted(missing_safety)}. Cannot confirm safety.",
        }

    title = _generate_title(candidate)
    branch = _generate_branch(candidate)
    body = _generate_body(pr_candidate)

    safety_all_zero = all(m.get("after", 0) == 0 for m in safety_found)

    return {
        "ready_to_create_pr": safety_all_zero,
        "candidate": candidate,
        "title": title,
        "branch_name": branch,
        "base_branch": "main",
        "body": body,
        "suggested_changed_files": pr_candidate.get("suggested_changed_files", []),
        "safety_note": "All safety metrics confirmed at 0. Human review required before merge." if safety_all_zero
                       else "Safety metrics NOT all zero. CHECK NEEDED.",
    }


def generate_report_md(metadata: dict) -> str:
    """Generate a readable report of the PR metadata."""
    lines = ["# PR Metadata Report", ""]
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    if not metadata.get("ready_to_create_pr"):
        lines.append(f"## Not Ready")
        lines.append("")
        lines.append(f"Candidate: {metadata.get('candidate', 'unknown')}")
        lines.append(f"Reason: {metadata.get('reason', '')}")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## Ready to Create PR: YES")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Title | `{metadata['title']}` |")
    lines.append(f"| Branch | `{metadata['branch_name']}` |")
    lines.append(f"| Base | `{metadata['base_branch']}` |")
    lines.append(f"| Safety | {metadata.get('safety_note', '')} |")
    lines.append("")

    if metadata.get("suggested_changed_files"):
        lines.append("## Suggested Changed Files")
        lines.append("")
        for f in metadata["suggested_changed_files"]:
            lines.append(f"- `{f}`")
        lines.append("")

    lines.append("## PR Body Preview")
    lines.append("")
    lines.append("```markdown")
    lines.append(metadata.get("body", ""))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Level 7: Generate PR metadata")
    parser.add_argument("--input", required=True, help="Path to level7_pr_candidate.json")
    parser.add_argument("--output", default="reports", help="Output directory")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: --input not found: {args.input}")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        pr_candidate = json.load(f)

    metadata = generate_metadata(pr_candidate)
    md = generate_report_md(metadata)

    os.makedirs(args.output, exist_ok=True)
    json_path = os.path.join(args.output, "level7_pr_metadata.json")
    md_path = os.path.join(args.output, "level7_pr_metadata.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    ready = metadata.get("ready_to_create_pr", False)
    print(f"Candidate: {metadata.get('candidate', 'unknown')}")
    print(f"Ready:     {ready}")
    if ready:
        print(f"Title:     {metadata['title']}")
        print(f"Branch:    {metadata['branch_name']}")
        print(f"Files:     {metadata.get('suggested_changed_files', [])}")
    else:
        print(f"Reason:    {metadata.get('reason', '')}")
    print(f"\nReports: {json_path}, {md_path}")


if __name__ == "__main__":
    main()
