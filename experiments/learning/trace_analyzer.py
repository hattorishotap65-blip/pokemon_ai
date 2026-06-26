"""
Analyze runtime advisor trace JSONL files.

Produces aggregate statistics on advisor usage, fallback reasons,
override rates, and action distributions.
"""
from __future__ import annotations
import json
from collections import Counter
from typing import Dict, List


def load_traces(path: str) -> List[dict]:
    try:
        entries = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries
    except (FileNotFoundError, OSError):
        return []


load_trace_entries = load_traces


def analyze_traces(entries: List[dict]) -> dict:
    """Aggregate trace entries into a summary dict."""
    total = len(entries)
    if total == 0:
        return {
            "total": 0, "advisor_used": 0, "advisor_used_rate": 0.0,
            "fallback_count": 0, "override_count": 0, "override_rate": 0.0,
            "fallback_reasons": {}, "advisor_top_actions": {},
            "existing_top_indices": {}, "avg_advisor_top_score": 0.0,
        }

    advisor_used = sum(1 for e in entries if e.get("used_advisor"))
    fallback_count = total - advisor_used
    override_count = sum(1 for e in entries if e.get("advisor_overrode_existing"))

    fallback_reasons = Counter()
    for e in entries:
        reason = e.get("fallback_reason")
        if reason:
            fallback_reasons[reason] += 1

    advisor_top_actions = Counter()
    advisor_scores_sum = 0.0
    advisor_scores_n = 0
    for e in entries:
        top = e.get("advisor_top")
        if top:
            advisor_top_actions[top] += 1
        scores = e.get("advisor_scores") or []
        if scores:
            advisor_scores_sum += scores[0].get("score", 0.0)
            advisor_scores_n += 1

    existing_top = Counter()
    for e in entries:
        idx = e.get("existing_top_index", -1)
        if idx >= 0:
            existing_top[str(idx)] += 1

    all_top_scores = []
    for e in entries:
        scores = e.get("advisor_scores") or []
        if scores:
            all_top_scores.append(scores[0].get("score", 0.0))

    selected_dist = Counter()
    for e in entries:
        for idx in (e.get("selected_indices") or []):
            selected_dist[str(idx)] += 1

    return {
        "total": total,
        "advisor_used": advisor_used,
        "advisor_used_rate": round(advisor_used / total, 4) if total else 0.0,
        "fallback_count": fallback_count,
        "override_count": override_count,
        "override_rate": round(override_count / total, 4) if total else 0.0,
        "fallback_reasons": dict(fallback_reasons.most_common()),
        "advisor_top_actions": dict(advisor_top_actions.most_common(10)),
        "existing_top_indices": dict(existing_top.most_common(5)),
        "avg_advisor_top_score": round(advisor_scores_sum / advisor_scores_n, 2) if advisor_scores_n else 0.0,
        "max_top_advisor_score": round(max(all_top_scores), 2) if all_top_scores else 0.0,
        "min_top_advisor_score": round(min(all_top_scores), 2) if all_top_scores else 0.0,
        "selected_index_distribution": dict(selected_dist.most_common(5)),
    }


summarize_traces = analyze_traces


def find_override_cases(entries: List[dict], limit: int = 20) -> List[dict]:
    """Extract entries where advisor overrode existing logic."""
    cases = []
    for e in entries:
        if e.get("advisor_overrode_existing"):
            cases.append({
                "ts": e.get("ts", 0),
                "advisor_top": e.get("advisor_top", ""),
                "advisor_top_index": e.get("advisor_top_index", -1),
                "existing_top_index": e.get("existing_top_index", -1),
                "advisor_score": (e.get("advisor_scores") or [{}])[0].get("score", 0.0),
                "state_active": (e.get("state_summary") or {}).get("active", ""),
            })
            if len(cases) >= limit:
                break
    return cases


def format_report(summary: dict, override_cases: List[dict] = None) -> str:
    """Format analysis summary as Markdown."""
    lines = ["# Advisor Trace Analysis", ""]

    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Total decisions | %d |" % summary.get("total", 0))
    lines.append("| Advisor used | %d (%.1f%%) |" % (
        summary.get("advisor_used", 0), summary.get("advisor_used_rate", 0) * 100))
    lines.append("| Fallback count | %d |" % summary.get("fallback_count", 0))
    lines.append("| Advisor overrode existing | %d (%.1f%%) |" % (
        summary.get("override_count", 0), summary.get("override_rate", 0) * 100))
    lines.append("| Avg advisor top score | %.2f |" % summary.get("avg_advisor_top_score", 0))
    lines.append("| Max advisor top score | %.2f |" % summary.get("max_top_advisor_score", 0))
    lines.append("| Min advisor top score | %.2f |" % summary.get("min_top_advisor_score", 0))
    lines.append("")

    reasons = summary.get("fallback_reasons", {})
    if reasons:
        lines.append("## Fallback Reasons")
        lines.append("")
        lines.append("| Reason | Count |")
        lines.append("|--------|-------|")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (reason, count))
        lines.append("")

    top_actions = summary.get("advisor_top_actions", {})
    if top_actions:
        lines.append("## Advisor Top Actions")
        lines.append("")
        lines.append("| Action | Count |")
        lines.append("|--------|-------|")
        for action, count in sorted(top_actions.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (action, count))
        lines.append("")

    if override_cases:
        lines.append("## Override Cases")
        lines.append("")
        lines.append("| Active | Advisor Top | Adv Idx | Existing Idx | Score |")
        lines.append("|--------|-------------|---------|--------------|-------|")
        for c in override_cases[:10]:
            lines.append("| %s | %s | %d | %d | %.1f |" % (
                c.get("state_active", ""), c.get("advisor_top", ""),
                c.get("advisor_top_index", -1), c.get("existing_top_index", -1),
                c.get("advisor_score", 0.0)))
        lines.append("")

    return "\n".join(lines)


render_markdown_report = format_report
