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
    }


def format_report(summary: dict) -> str:
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

    return "\n".join(lines)
