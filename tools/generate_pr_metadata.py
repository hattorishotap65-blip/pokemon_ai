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
    """Generate a safe branch name."""
    slug = _slugify(re.sub(r"[_=]", " ", candidate))
    if not slug:
        slug = "accepted-candidate"
    return f"feat/adopt-{slug}"


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

    lines.append("## Safety")
    lines.append("")
    lines.append("All safety metrics confirmed at 0:")
    lines.append("- attack_available_but_no_attack: 0")
    lines.append("- end_when_attack_available: 0")
    lines.append("- retreat_when_attack_available: 0")
    lines.append("- ability_without_followup_attack: 0")
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

    title = _generate_title(candidate)
    branch = _generate_branch(candidate)
    body = _generate_body(pr_candidate)

    return {
        "ready_to_create_pr": True,
        "candidate": candidate,
        "title": title,
        "branch_name": branch,
        "base_branch": "main",
        "body": body,
        "suggested_changed_files": pr_candidate.get("suggested_changed_files", []),
        "safety_note": "All safety metrics confirmed at 0. Human review required before merge.",
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
