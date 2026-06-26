"""
Generate tuning recommendations from advisor trace analysis.

Identifies which weights/features/labels need adjustment based on
fallback patterns, override conflicts, and score distributions.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from experiments.learning.trace_analyzer import analyze_traces, find_override_cases


def _action_key_from_entry(entry: dict) -> str:
    top = entry.get("advisor_top")
    if top:
        return top
    cands = entry.get("candidates") or []
    if cands:
        return cands[0].get("id", "unknown")
    return "unknown"


def _collect_zero_score_actions(entries: List[dict]) -> Counter:
    actions = Counter()
    for e in entries:
        if e.get("fallback_reason") != "all_scores_zero":
            continue
        for c in (e.get("candidates") or []):
            ctype = c.get("type", "unknown")
            cid = c.get("id", "")
            actions[ctype] += 1
            if cid:
                actions["id:" + cid] += 1
    return actions


def _collect_override_patterns(entries: List[dict]) -> List[dict]:
    patterns = Counter()
    for e in entries:
        if not e.get("advisor_overrode_existing"):
            continue
        adv = e.get("advisor_top", "?")
        existing_idx = e.get("existing_top_index", -1)
        patterns["%s_over_idx%d" % (adv, existing_idx)] += 1
    return [{"pattern": k, "count": v} for k, v in patterns.most_common(10)]


def _build_action_hotspots(entries: List[dict]) -> List[dict]:
    """Per advisor_top action: count, override_count, avg_score, example_active."""
    by_action: Dict[str, dict] = defaultdict(
        lambda: {"count": 0, "override": 0, "score_sum": 0.0, "example_active": ""}
    )
    for e in entries:
        top = e.get("advisor_top")
        if not top:
            continue
        h = by_action[top]
        h["count"] += 1
        if e.get("advisor_overrode_existing"):
            h["override"] += 1
        scores = e.get("advisor_scores") or []
        if scores:
            h["score_sum"] += scores[0].get("score", 0.0)
        if not h["example_active"]:
            h["example_active"] = (e.get("state_summary") or {}).get("active", "")

    result = []
    for action, h in sorted(by_action.items(), key=lambda x: -x[1]["count"]):
        result.append({
            "action": action,
            "count": h["count"],
            "override_count": h["override"],
            "avg_score": round(h["score_sum"] / h["count"], 2) if h["count"] else 0.0,
            "example_active": h["example_active"],
        })
    return result


def _build_fallback_hotspots(entries: List[dict]) -> List[dict]:
    """Per fallback_reason: count, example candidate types."""
    by_reason: Dict[str, dict] = defaultdict(
        lambda: {"count": 0, "example_types": Counter()}
    )
    for e in entries:
        reason = e.get("fallback_reason")
        if not reason:
            continue
        h = by_reason[reason]
        h["count"] += 1
        for c in (e.get("candidates") or [])[:3]:
            h["example_types"][c.get("type", "unknown")] += 1

    result = []
    for reason, h in sorted(by_reason.items(), key=lambda x: -x[1]["count"]):
        result.append({
            "reason": reason,
            "count": h["count"],
            "example_types": dict(h["example_types"].most_common(5)),
        })
    return result


def _build_signals(summary: dict, entries: List[dict]) -> List[dict]:
    """Extract key signals from summary."""
    signals = []
    total = summary.get("total", 0)
    if total == 0:
        return signals

    fallback_reasons = summary.get("fallback_reasons", {})
    zero_count = fallback_reasons.get("all_scores_zero", 0)
    if zero_count >= 5 or (total > 0 and zero_count / total >= 0.2):
        signals.append({"signal": "high_zero_score_rate", "value": zero_count, "rate": round(zero_count / total, 3)})

    wm = fallback_reasons.get("weights_missing", 0)
    if wm > 0:
        signals.append({"signal": "weights_missing", "value": wm})

    advisor_rate = summary.get("advisor_used_rate", 0)
    if total >= 10 and advisor_rate < 0.20:
        signals.append({"signal": "low_advisor_coverage", "value": round(advisor_rate, 3)})

    override_rate = summary.get("override_rate", 0)
    if total > 0 and override_rate > 0.3:
        signals.append({"signal": "high_override_rate", "value": round(override_rate, 3)})

    top_actions = summary.get("advisor_top_actions", {})
    if top_actions:
        top_action, top_count = next(iter(top_actions.items()))
        advisor_used = summary.get("advisor_used", 1)
        if advisor_used > 0 and top_count / advisor_used >= 0.5:
            signals.append({"signal": "dominant_action", "action": top_action,
                            "rate": round(top_count / advisor_used, 3)})

    return signals


def _make_rec(priority, issue, detail, suggestion, **extra):
    rec = {
        "priority": priority,
        "category": issue.split("_")[0] if "_" in issue else issue,
        "title": issue,
        "issue": issue,
        "reason": detail,
        "detail": detail,
        "suggested_action": suggestion,
        "suggestion": suggestion,
    }
    rec.update(extra)
    return rec


def build_tuning_recommendations(
    entries: List[dict], summary: Optional[dict] = None,
) -> dict:
    if summary is None:
        summary = analyze_traces(entries)

    total = summary.get("total", 0)
    recs: List[dict] = []

    fallback_reasons = summary.get("fallback_reasons", {})
    zero_count = fallback_reasons.get("all_scores_zero", 0)
    if zero_count >= 5 or (total > 0 and zero_count / total >= 0.2):
        zero_actions = _collect_zero_score_actions(entries)
        missing_types = [k for k, v in zero_actions.most_common(5) if not k.startswith("id:")]
        recs.append(_make_rec(
            "high", "all_scores_zero_rate_high",
            "%.0f%% (%d) decisions fell back due to all scores being zero" % (
                zero_count / total * 100 if total else 0, zero_count),
            "Add feature extraction rules for these action types, or add weights for their features",
            affected_types=missing_types,
        ))

    wm_count = fallback_reasons.get("weights_missing", 0)
    if wm_count > 0:
        recs.append(_make_rec(
            "high", "weights_missing",
            "%d decisions had no weights loaded" % wm_count,
            "Check POKEMON_AI_WEIGHTS_PATH and ensure weights JSON exists",
        ))

    advisor_rate = summary.get("advisor_used_rate", 0)
    if total >= 10 and advisor_rate < 0.20:
        recs.append(_make_rec(
            "medium", "low_advisor_usage",
            "Advisor used only %.0f%% of the time" % (advisor_rate * 100),
            "Improve feature coverage so more actions get non-zero scores",
        ))

    override_count = summary.get("override_count", 0)
    if total > 0 and override_count / total > 0.3:
        patterns = _collect_override_patterns(entries)
        recs.append(_make_rec(
            "medium", "high_override_rate",
            "Advisor overrides existing logic %.0f%% of the time" % (override_count / total * 100),
            "Review override cases to verify advisor decisions are correct",
            top_patterns=patterns[:5],
        ))

    top_actions = summary.get("advisor_top_actions", {})
    if top_actions:
        top_action, top_count = next(iter(top_actions.items()))
        advisor_used = summary.get("advisor_used", 1)
        if advisor_used > 0 and top_count / advisor_used >= 0.5:
            recs.append(_make_rec(
                "low", "dominant_single_action",
                "'%s' chosen %.0f%% of advisor decisions" % (top_action, top_count / advisor_used * 100),
                "Check if weight for this action is disproportionately high",
            ))

    max_score = summary.get("max_top_advisor_score", 0)
    min_score = summary.get("min_top_advisor_score", 0)
    if max_score > 0 and max_score - min_score < 5:
        recs.append(_make_rec(
            "low", "narrow_score_range",
            "Score range is only %.1f (max=%.1f, min=%.1f)" % (max_score - min_score, max_score, min_score),
            "Increase weight magnitudes or add more discriminating features",
        ))

    if not recs:
        recs.append(_make_rec(
            "info", "no_issues_found",
            "Trace analysis found no obvious tuning opportunities",
            "Collect more trace data or try different weight values",
        ))

    return {
        "total_entries": total,
        "signals": _build_signals(summary, entries),
        "recommendations": recs,
        "action_hotspots": _build_action_hotspots(entries),
        "fallback_hotspots": _build_fallback_hotspots(entries),
        "zero_score_action_types": dict(_collect_zero_score_actions(entries).most_common(10)),
        "override_patterns": _collect_override_patterns(entries),
    }


def render_recommendation_report(recommendations: dict) -> str:
    lines = ["# Advisor Tuning Recommendations", ""]

    lines.append("## Summary")
    lines.append("")
    lines.append("Total trace entries: %d" % recommendations.get("total_entries", 0))
    lines.append("")

    signals = recommendations.get("signals", [])
    if signals:
        lines.append("## Key Signals")
        lines.append("")
        lines.append("| Signal | Value |")
        lines.append("|--------|-------|")
        for s in signals:
            val = s.get("rate", s.get("value", ""))
            lines.append("| %s | %s |" % (s["signal"], val))
        lines.append("")

    recs = recommendations.get("recommendations", [])
    if recs:
        lines.append("## Recommendations")
        lines.append("")
        for i, r in enumerate(recs, 1):
            lines.append("### %d. [%s] %s" % (i, r.get("priority", "?").upper(), r.get("title", r.get("issue", ""))))
            lines.append("")
            lines.append(r.get("detail", r.get("reason", "")))
            lines.append("")
            lines.append("**Suggestion:** %s" % r.get("suggested_action", r.get("suggestion", "")))
            lines.append("")
            if "affected_types" in r:
                lines.append("Affected types: %s" % ", ".join(r["affected_types"]))
                lines.append("")
            if "top_patterns" in r:
                lines.append("| Pattern | Count |")
                lines.append("|---------|-------|")
                for p in r["top_patterns"]:
                    lines.append("| %s | %d |" % (p["pattern"], p["count"]))
                lines.append("")

    fallback_hs = recommendations.get("fallback_hotspots", [])
    if fallback_hs:
        lines.append("## Fallback Hotspots")
        lines.append("")
        lines.append("| Reason | Count | Example Types |")
        lines.append("|--------|-------|---------------|")
        for h in fallback_hs:
            types_str = ", ".join(h.get("example_types", {}).keys())
            lines.append("| %s | %d | %s |" % (h["reason"], h["count"], types_str))
        lines.append("")

    action_hs = recommendations.get("action_hotspots", [])
    if action_hs:
        lines.append("## Action Hotspots")
        lines.append("")
        lines.append("| Action | Count | Overrides | Avg Score | Example Active |")
        lines.append("|--------|-------|-----------|-----------|----------------|")
        for h in action_hs[:10]:
            lines.append("| %s | %d | %d | %.1f | %s |" % (
                h["action"], h["count"], h["override_count"], h["avg_score"], h["example_active"]))
        lines.append("")

    lines.append("## Next Suggested PR")
    lines.append("")
    if any(r.get("priority") == "high" for r in recs):
        lines.append("Address high-priority issues first (feature coverage, weights config).")
    elif any(r.get("priority") == "medium" for r in recs):
        lines.append("Review medium-priority issues (advisor coverage, override cases).")
    else:
        lines.append("No critical issues. Collect more trace data or experiment with weight values.")
    lines.append("")

    return "\n".join(lines)
