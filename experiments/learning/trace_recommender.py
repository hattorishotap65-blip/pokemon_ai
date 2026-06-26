"""
Generate tuning recommendations from advisor trace analysis.

Identifies which weights/features/labels need adjustment based on
fallback patterns, override conflicts, and score distributions.
"""
from __future__ import annotations
from collections import Counter
from typing import Dict, List, Optional

from experiments.learning.trace_analyzer import analyze_traces, find_override_cases


def _action_key_from_entry(entry: dict) -> str:
    """Extract a representative action key from a trace entry."""
    top = entry.get("advisor_top")
    if top:
        return top
    cands = entry.get("candidates") or []
    if cands:
        return cands[0].get("id", "unknown")
    return "unknown"


def _collect_zero_score_actions(entries: List[dict]) -> Counter:
    """Count which candidate types/ids appear when all_scores_zero."""
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
    """Summarize advisor override patterns."""
    patterns = Counter()
    for e in entries:
        if not e.get("advisor_overrode_existing"):
            continue
        adv = e.get("advisor_top", "?")
        existing_idx = e.get("existing_top_index", -1)
        patterns["%s_over_idx%d" % (adv, existing_idx)] += 1
    return [{"pattern": k, "count": v} for k, v in patterns.most_common(10)]


def build_tuning_recommendations(
    entries: List[dict], summary: Optional[dict] = None,
) -> dict:
    """Analyze traces and produce tuning recommendations."""
    if summary is None:
        summary = analyze_traces(entries)

    total = summary.get("total", 0)
    recs: List[dict] = []

    # 1. High all_scores_zero rate
    fallback_reasons = summary.get("fallback_reasons", {})
    zero_count = fallback_reasons.get("all_scores_zero", 0)
    if total > 0 and zero_count / total > 0.2:
        zero_actions = _collect_zero_score_actions(entries)
        missing_types = [k for k, v in zero_actions.most_common(5) if not k.startswith("id:")]
        recs.append({
            "priority": "high",
            "issue": "all_scores_zero_rate_high",
            "detail": "%.0f%% of decisions fell back due to all scores being zero" % (zero_count / total * 100),
            "affected_types": missing_types,
            "suggestion": "Add feature extraction rules for these action types, or add weights for their features",
        })

    # 2. weights_missing
    wm_count = fallback_reasons.get("weights_missing", 0)
    if wm_count > 0:
        recs.append({
            "priority": "high",
            "issue": "weights_missing",
            "detail": "%d decisions had no weights loaded" % wm_count,
            "suggestion": "Check POKEMON_AI_WEIGHTS_PATH and ensure weights JSON exists",
        })

    # 3. Low advisor usage
    advisor_rate = summary.get("advisor_used_rate", 0)
    if total > 0 and advisor_rate < 0.3:
        recs.append({
            "priority": "medium",
            "issue": "low_advisor_usage",
            "detail": "Advisor used only %.0f%% of the time" % (advisor_rate * 100),
            "suggestion": "Improve feature coverage so more actions get non-zero scores",
        })

    # 4. Override conflicts
    override_count = summary.get("override_count", 0)
    if total > 0 and override_count / total > 0.3:
        patterns = _collect_override_patterns(entries)
        recs.append({
            "priority": "medium",
            "issue": "high_override_rate",
            "detail": "Advisor overrides existing logic %.0f%% of the time" % (override_count / total * 100),
            "top_patterns": patterns[:5],
            "suggestion": "Review override cases to verify advisor decisions are correct before increasing weight influence",
        })

    # 5. Dominant single action
    top_actions = summary.get("advisor_top_actions", {})
    if top_actions:
        top_action, top_count = next(iter(top_actions.items()))
        advisor_used = summary.get("advisor_used", 1)
        if advisor_used > 0 and top_count / advisor_used > 0.6:
            recs.append({
                "priority": "low",
                "issue": "dominant_single_action",
                "detail": "'%s' chosen %.0f%% of advisor decisions" % (top_action, top_count / advisor_used * 100),
                "suggestion": "Check if weight for this action is disproportionately high, or if other actions lack features",
            })

    # 6. Score range
    max_score = summary.get("max_top_advisor_score", 0)
    min_score = summary.get("min_top_advisor_score", 0)
    if max_score > 0 and max_score - min_score < 5:
        recs.append({
            "priority": "low",
            "issue": "narrow_score_range",
            "detail": "Score range is only %.1f (max=%.1f, min=%.1f)" % (max_score - min_score, max_score, min_score),
            "suggestion": "Increase weight magnitudes or add more discriminating features",
        })

    if not recs:
        recs.append({
            "priority": "info",
            "issue": "no_issues_found",
            "detail": "Trace analysis found no obvious tuning opportunities",
            "suggestion": "Collect more trace data or try different weight values",
        })

    return {
        "total_entries": total,
        "recommendations": recs,
        "zero_score_action_types": dict(_collect_zero_score_actions(entries).most_common(10)),
        "override_patterns": _collect_override_patterns(entries),
    }


def render_recommendation_report(recommendations: dict) -> str:
    """Render tuning recommendations as Markdown."""
    lines = ["# Advisor Tuning Recommendations", ""]
    lines.append("Total trace entries analyzed: %d" % recommendations.get("total_entries", 0))
    lines.append("")

    recs = recommendations.get("recommendations", [])
    if recs:
        lines.append("## Recommendations")
        lines.append("")
        for i, r in enumerate(recs, 1):
            lines.append("### %d. [%s] %s" % (i, r.get("priority", "?").upper(), r.get("issue", "")))
            lines.append("")
            lines.append(r.get("detail", ""))
            lines.append("")
            lines.append("**Suggestion:** %s" % r.get("suggestion", ""))
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

    zero_types = recommendations.get("zero_score_action_types", {})
    if zero_types:
        lines.append("## Zero-Score Action Types")
        lines.append("")
        lines.append("| Type/ID | Count |")
        lines.append("|---------|-------|")
        for k, v in sorted(zero_types.items(), key=lambda x: -x[1])[:10]:
            lines.append("| %s | %d |" % (k, v))
        lines.append("")

    return "\n".join(lines)
