"""
Compare before/after anomaly reports and produce an A/B comparison with a decision.

Usage:
  python tools/compare_anomaly_reports.py \
    --before reports/baseline/latest_anomaly_report.json \
    --after reports/candidate/latest_anomaly_report.json \
    --output reports

  python tools/compare_anomaly_reports.py \
    --before reports/baseline/latest_anomaly_report.json \
    --after reports/candidate/latest_anomaly_report.json \
    --output reports \
    --min-games 20

Outputs:
  reports/latest_ab_comparison.json
  reports/latest_ab_comparison.md
  reports/comparisons/<dated>.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Metrics to compare
# ---------------------------------------------------------------------------

_SEVERITY_KEYS = ["critical", "high", "medium", "low"]

_ANOMALY_TYPE_KEYS = [
    "attack_available_but_no_attack",
    "end_when_attack_available",
    "retreat_when_attack_available",
    "ability_without_followup_attack",
    "high_value_attack_not_used",
    "ko_available_but_no_attack",
    "ability_breaks_attack_ready_state",
    "overattach_to_ready_attacker",
    "stage1_without_base_search",
    "duplicate_stage1_search",
    "low_value_search",
    "discarded_protected_card",
    "stronger_ready_bench_attacker_not_promoted",
]

_ALL_METRIC_KEYS = (
    ["anomalies_total"] + _SEVERITY_KEYS + _ANOMALY_TYPE_KEYS
)


# ---------------------------------------------------------------------------
# Pure comparison functions
# ---------------------------------------------------------------------------

def load_summary(path: str) -> dict:
    """Load an anomaly report JSON and return its summary dict."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("summary", {})


def compute_metrics(before: dict, after: dict) -> list[dict]:
    """Compare each metric between before and after summaries."""
    metrics = []
    for key in _ALL_METRIC_KEYS:
        b = before.get(key, 0)
        a = after.get(key, 0)
        delta = a - b
        if delta < 0:
            direction = "improved"
        elif delta > 0:
            direction = "worsened"
        else:
            direction = "unchanged"
        metrics.append({
            "name":      key,
            "before":    b,
            "after":     a,
            "delta":     delta,
            "direction": direction,
        })
    return metrics


def decide(
    before: dict, after: dict, metrics: list[dict],
    min_games: int = 20,
) -> tuple[str, list[str], list[str]]:
    """
    Return (decision, reasons, warnings).

    decision is one of: accept, reject, needs_more_games, human_review.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    games_before = before.get("games", 0)
    games_after  = after.get("games", 0)

    # --- needs_more_games ---
    if games_before < min_games or games_after < min_games:
        warnings.append(
            f"Game count below minimum ({min_games}): "
            f"before={games_before}, after={games_after}."
        )
        return "needs_more_games", ["Insufficient game count for reliable comparison."], warnings

    m_by_name = {m["name"]: m for m in metrics}

    total_delta    = m_by_name["anomalies_total"]["delta"]
    critical_delta = m_by_name["critical"]["delta"]
    high_delta     = m_by_name["high"]["delta"]

    # --- reject ---
    if critical_delta > 0:
        reasons.append(f"Critical anomalies increased by {critical_delta}.")
        return "reject", reasons, warnings

    if high_delta > 2:
        reasons.append(f"High anomalies increased significantly (+{high_delta}).")
        return "reject", reasons, warnings

    if total_delta > 0 and critical_delta >= 0 and high_delta >= 0:
        reasons.append(f"Total anomalies increased (+{total_delta}) with no severity improvement.")
        return "reject", reasons, warnings

    # --- accept ---
    improved = [m for m in metrics if m["direction"] == "improved"]
    worsened = [m for m in metrics if m["direction"] == "worsened"]

    if total_delta < 0 and critical_delta <= 0 and high_delta <= 0:
        reasons.append("Total anomalies decreased.")
        if critical_delta < 0:
            reasons.append("Critical anomalies decreased.")
        if high_delta < 0:
            reasons.append("High severity anomalies decreased.")
        if not worsened:
            reasons.append("No metric worsened.")
            return "accept", reasons, warnings
        minor_worsen = all(
            m["name"] in ("low", "info") or abs(m["delta"]) <= 1
            for m in worsened
        )
        if minor_worsen:
            reasons.append("Worsened metrics are minor (low/info or delta<=1).")
            return "accept", reasons, warnings

    # --- human_review (mixed signals) ---
    if improved and worsened:
        reasons.append("Improvement and worsening are mixed across metrics.")
    if total_delta == 0:
        reasons.append("Total anomalies unchanged — no clear signal.")
    if total_delta < 0 and high_delta == 0:
        reasons.append("Total improved but high severity unchanged.")

    return "human_review", reasons, warnings


def build_comparison_json(
    before_path: str, after_path: str,
    before_summary: dict, after_summary: dict,
    metrics: list[dict],
    decision: str, reasons: list[str], warnings: list[str],
) -> dict:
    """Build the full A/B comparison JSON structure."""
    m_by_name = {m["name"]: m for m in metrics}
    return {
        "schema_version": "1.0",
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "before":         before_path,
        "after":          after_path,
        "summary": {
            "decision":       decision,
            "overall_delta":  m_by_name["anomalies_total"]["delta"],
            "critical_delta": m_by_name["critical"]["delta"],
            "high_delta":     m_by_name["high"]["delta"],
            "medium_delta":   m_by_name["medium"]["delta"],
            "low_delta":      m_by_name["low"]["delta"],
            "games_before":   before_summary.get("games", 0),
            "games_after":    after_summary.get("games", 0),
            "confidence":     "high" if min(
                before_summary.get("games", 0), after_summary.get("games", 0)
            ) >= 50 else "medium",
        },
        "metrics":  metrics,
        "reasons":  reasons,
        "warnings": warnings,
    }


def build_comparison_markdown(
    comparison: dict,
) -> str:
    """Build human-readable Markdown from comparison JSON."""
    s   = comparison["summary"]
    met = comparison["metrics"]
    lines = ["# A/B Anomaly Comparison", ""]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"Generated: {ts}")
    lines.append("")

    lines.append("## Decision")
    lines.append("")
    lines.append(f"**{s['decision']}**")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    for key in ["anomalies_total", "critical", "high", "medium", "low"]:
        m = next((x for x in met if x["name"] == key), None)
        if m:
            sign = "+" if m["delta"] > 0 else ""
            lines.append(f"- {key}: {m['before']} -> {m['after']} ({sign}{m['delta']})")
    lines.append(f"- games: {s['games_before']} (before) / {s['games_after']} (after)")
    lines.append(f"- confidence: {s['confidence']}")
    lines.append("")

    improved = [m for m in met if m["direction"] == "improved" and m["name"] not in _SEVERITY_KEYS + ["anomalies_total"]]
    worsened = [m for m in met if m["direction"] == "worsened" and m["name"] not in _SEVERITY_KEYS + ["anomalies_total"]]

    if improved:
        lines.append("## Improved")
        lines.append("")
        for m in improved:
            lines.append(f"- {m['name']}: {m['before']} -> {m['after']} ({m['delta']})")
        lines.append("")

    if worsened:
        lines.append("## Worsened")
        lines.append("")
        for m in worsened:
            lines.append(f"- {m['name']}: {m['before']} -> {m['after']} (+{m['delta']})")
        lines.append("")

    if comparison.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        for w in comparison["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    if comparison.get("reasons"):
        lines.append("## Reasons")
        lines.append("")
        for r in comparison["reasons"]:
            lines.append(f"- {r}")
        lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    rec = {
        "accept":           "Candidate is safe to adopt.",
        "reject":           "Candidate should be rejected — severity increased.",
        "needs_more_games": "Run more games before deciding.",
        "human_review":     "Mixed signals — human review recommended.",
    }
    lines.append(rec.get(s["decision"], "Review manually."))
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare before/after anomaly reports"
    )
    parser.add_argument("--before", required=True, help="Path to baseline anomaly report JSON")
    parser.add_argument("--after",  required=True, help="Path to candidate anomaly report JSON")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--min-games", type=int, default=20, help="Minimum games for reliable comparison")
    args = parser.parse_args()

    if not os.path.exists(args.before):
        print(f"Error: --before file not found: {args.before}")
        sys.exit(1)
    if not os.path.exists(args.after):
        print(f"Error: --after file not found: {args.after}")
        sys.exit(1)

    before_summary = load_summary(args.before)
    after_summary  = load_summary(args.after)
    metrics        = compute_metrics(before_summary, after_summary)
    decision, reasons, warnings = decide(
        before_summary, after_summary, metrics,
        min_games=args.min_games,
    )

    comparison = build_comparison_json(
        args.before, args.after,
        before_summary, after_summary,
        metrics, decision, reasons, warnings,
    )
    md = build_comparison_markdown(comparison)

    os.makedirs(args.output, exist_ok=True)
    os.makedirs(os.path.join(args.output, "comparisons"), exist_ok=True)

    json_path = os.path.join(args.output, "latest_ab_comparison.json")
    md_path   = os.path.join(args.output, "latest_ab_comparison.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dated_path = os.path.join(args.output, "comparisons", f"ab_comparison_{ts}.json")
    with open(dated_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)

    print(f"Decision: {decision}")
    print(f"  Total anomalies: {before_summary.get('anomalies_total', 0)} -> {after_summary.get('anomalies_total', 0)}")
    for r in reasons:
        print(f"  - {r}")
    if warnings:
        for w in warnings:
            print(f"  [WARN] {w}")
    print(f"\nReports written:")
    print(f"  {json_path}")
    print(f"  {md_path}")
    print(f"  {dated_path}")


if __name__ == "__main__":
    main()
