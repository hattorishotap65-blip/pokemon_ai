"""
Generate JSON, Markdown, and LLM summary reports from anomaly detection results.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone


def generate_json_report(
    anomalies: list[dict],
    summary: dict,
    deck_profile_id: str = "unknown",
    source_dir: str = "battle_logs/inbox",
) -> dict:
    """Build the full JSON report structure."""
    return {
        "schema_version":  "1.0",
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "deck_profile_id": deck_profile_id,
        "source_dir":      source_dir,
        "summary":         summary,
        "anomalies":       anomalies,
    }


def generate_markdown_report(
    anomalies: list[dict],
    summary: dict,
    top_n: int = 20,
) -> str:
    """Build human-readable Markdown report."""
    lines = ["# Battle Log Anomaly Report", ""]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"Generated: {ts}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")
    for key in ["files", "games", "turns", "actions", "anomalies_total"]:
        lines.append(f"| {key} | {summary.get(key, 0)} |")
    lines.append("")

    # Severity breakdown
    lines.append("## Severity Breakdown")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in ["critical", "high", "medium", "low", "info"]:
        cnt = summary.get(sev, 0)
        if cnt > 0:
            lines.append(f"| {sev} | {cnt} |")
    lines.append("")

    # Top issue types
    type_counts = Counter(a["type"] for a in anomalies)
    if type_counts:
        lines.append("## Top Issues")
        lines.append("")
        for atype, cnt in type_counts.most_common(10):
            fix_areas = set()
            for a in anomalies:
                if a["type"] == atype:
                    fix_areas.update(a.get("suggested_fix_area", []))
            lines.append(f"### {atype}")
            lines.append(f"- count: {cnt}")
            if fix_areas:
                lines.append(f"- likely fix area: {', '.join(sorted(fix_areas))}")
            lines.append("")

    # Representative anomalies
    if anomalies:
        lines.append("## Representative Anomalies")
        lines.append("")
        for a in anomalies[:top_n]:
            lines.append(f"### {a['id']}")
            lines.append(f"- severity: {a['severity']}")
            lines.append(f"- type: {a['type']}")
            lines.append(f"- file: {a.get('file', '')}")
            lines.append(f"- turn: {a.get('turn', '')}")
            active_label = a.get("active_name") or a.get("active_id") or "unknown"
            lines.append(f"- active: {active_label}")
            lines.append(f"- expected: {a.get('expected_action', '')}")
            lines.append(f"- actual: {a.get('actual_action', '')}")
            lines.append(f"- why suspicious: {a.get('why_suspicious', '')}")
            if a.get("suggested_fix_area"):
                lines.append(f"- suggested fix area: {', '.join(a['suggested_fix_area'])}")
            lines.append("")

    # Suggested next actions
    lines.append("## Suggested Next Actions")
    lines.append("")
    if not anomalies:
        lines.append("No anomalies detected. Logs look clean.")
    else:
        if summary.get("critical", 0) > 0:
            lines.append("1. **Investigate critical anomalies first** — KO misses and End-when-attack-available are highest priority.")
        if summary.get("high", 0) > 0:
            lines.append("2. Check high-severity issues — attack misses and retreat-when-attack-available.")
        if summary.get("medium", 0) > 0:
            lines.append("3. Review medium-severity patterns for scoring weight adjustments.")
        lines.append(f"4. Run a targeted simulation to verify fixes (50+ games recommended).")
    lines.append("")

    return "\n".join(lines)


def generate_llm_summary(
    anomalies: list[dict],
    summary: dict,
    top_n: int = 10,
) -> str:
    """Build a short LLM-friendly review packet."""
    lines = ["# LLM Review Packet", ""]

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total anomalies: {summary.get('anomalies_total', 0)}")
    lines.append(f"- critical: {summary.get('critical', 0)}")
    lines.append(f"- high: {summary.get('high', 0)}")
    lines.append(f"- medium: {summary.get('medium', 0)}")
    lines.append(f"- low: {summary.get('low', 0)}")

    type_counts = Counter(a["type"] for a in anomalies)
    if type_counts:
        most_common_type, most_common_cnt = type_counts.most_common(1)[0]
        lines.append(f"- most common issue: {most_common_type} ({most_common_cnt})")
        fix_areas: set[str] = set()
        for a in anomalies:
            if a["type"] == most_common_type:
                fix_areas.update(a.get("suggested_fix_area", []))
        if fix_areas:
            lines.append(f"- likely fix area: {', '.join(sorted(fix_areas))}")
    lines.append("")

    # Top anomalies
    if anomalies:
        lines.append(f"## Top {min(top_n, len(anomalies))} Anomalies")
        lines.append("")
        for a in anomalies[:top_n]:
            lines.append(f"### {a['id']}")
            lines.append(f"- type: {a['type']}")
            lines.append(f"- severity: {a['severity']}")
            active_label = a.get("active_name") or a.get("active_id") or "unknown"
            lines.append(f"- active: {active_label}")
            lines.append(f"- expected: {a.get('expected_action', '')}")
            lines.append(f"- actual: {a.get('actual_action', '')}")
            lines.append(f"- why suspicious: {a.get('why_suspicious', '')}")
            if a.get("suggested_fix_area"):
                lines.append(f"- suggested fix area: {', '.join(a['suggested_fix_area'])}")
            lines.append("")

    # Ask section
    lines.append("## Ask")
    lines.append("")
    lines.append("Please identify:")
    lines.append("1. likely root cause")
    lines.append("2. file to inspect")
    lines.append("3. profile or weight change candidate")
    lines.append("4. whether code change is needed")
    lines.append("5. whether an A/B simulation is required")
    lines.append("")

    return "\n".join(lines)
