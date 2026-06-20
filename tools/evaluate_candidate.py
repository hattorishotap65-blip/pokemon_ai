"""
Level 7-lite: Candidate evaluation gate.

Compares baseline vs candidate anomaly reports and produces an
accept / hold / reject decision with reasons.

Usage:
  python tools/evaluate_candidate.py \
    --before reports/baseline/latest_anomaly_report.json \
    --after reports/candidate/latest_anomaly_report.json \
    --candidate "retreat_bonus=1400" \
    --output reports

  python tools/evaluate_candidate.py \
    --before reports/baseline/latest_anomaly_report.json \
    --after reports/candidate/latest_anomaly_report.json \
    --candidate "F0009 KW-only" \
    --min-games 50 \
    --output reports
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Safety metrics — must not worsen
# ---------------------------------------------------------------------------

_SAFETY_METRICS = [
    "attack_available_but_no_attack",
    "end_when_attack_available",
    "retreat_when_attack_available",
    "ability_without_followup_attack",
]

# Metrics where lower is better
_LOWER_IS_BETTER = [
    "anomalies_total",
    "attack_available_but_no_attack",
    "end_when_attack_available",
    "retreat_when_attack_available",
    "ability_without_followup_attack",
    "voltorb_over_wattrel_missed",
    "voltorb_over_kilowattrel_missed",
    "bellibolt_over_voltorb_high_damage",
    "error_rate",
    "fallback_rate",
    "p95_decision_time_ms",
    "avg_decision_time_ms",
]

# Metrics where higher is better
_HIGHER_IS_BETTER = [
    "win_rate",
]

_ALL_METRICS = [
    "anomalies_total",
    "error_rate",
    "fallback_rate",
    "avg_decision_time_ms",
    "p95_decision_time_ms",
    "attack_available_but_no_attack",
    "end_when_attack_available",
    "retreat_when_attack_available",
    "ability_without_followup_attack",
    "voltorb_over_wattrel_missed",
    "voltorb_over_kilowattrel_missed",
    "bellibolt_over_voltorb_high_damage",
    "win_rate",
]


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def load_summary(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("summary", {})


def evaluate(
    before: dict, after: dict,
    candidate_name: str = "unknown",
    min_games: int = 20,
) -> dict:
    """Evaluate candidate vs baseline. Returns evaluation result dict."""
    games_before = before.get("games", 0)
    games_after = after.get("games", 0)

    improved = []
    worsened = []
    safe = []
    missing = []
    reasons = []

    for metric in _ALL_METRICS:
        bv = before.get(metric)
        cv = after.get(metric)

        if bv is None or cv is None:
            missing.append(metric)
            continue

        # Normalize per-game for count metrics
        bg = games_before if games_before > 0 else 1
        cg = games_after if games_after > 0 else 1

        if metric in ("win_rate", "error_rate", "fallback_rate",
                      "avg_decision_time_ms", "p95_decision_time_ms"):
            b_rate = bv
            c_rate = cv
        else:
            b_rate = bv / bg
            c_rate = cv / cg

        delta = c_rate - b_rate

        entry = {
            "metric": metric,
            "before": round(b_rate, 4),
            "after": round(c_rate, 4),
            "delta": round(delta, 4),
        }

        if metric in _LOWER_IS_BETTER:
            if delta < -0.01:
                entry["direction"] = "improved"
                improved.append(entry)
            elif delta > 0.01:
                entry["direction"] = "worsened"
                worsened.append(entry)
            else:
                entry["direction"] = "unchanged"
                safe.append(entry)
        elif metric in _HIGHER_IS_BETTER:
            if delta > 0.01:
                entry["direction"] = "improved"
                improved.append(entry)
            elif delta < -0.01:
                entry["direction"] = "worsened"
                worsened.append(entry)
            else:
                entry["direction"] = "unchanged"
                safe.append(entry)
        else:
            safe.append(entry)

    # --- Decision logic ---

    # Check game count
    if games_before < min_games or games_after < min_games:
        reasons.append(f"Insufficient games: before={games_before}, after={games_after} (min={min_games})")
        return _build_result(candidate_name, "hold", improved, worsened, safe, missing, reasons,
                            "Run more games before deciding.", games_before, games_after)

    # Check safety: candidate must have all safety metrics at 0
    bg = max(games_before, 1)
    cg = max(games_after, 1)
    safety_broken = False
    for metric in _SAFETY_METRICS:
        cv = after.get(metric, 0)
        if cv > 0:
            safety_broken = True
            reasons.append(f"Safety not zero: {metric} = {cv} in candidate")

    if safety_broken:
        return _build_result(candidate_name, "reject", improved, worsened, safe, missing, reasons,
                            "Revert candidate. Safety metrics worsened.", games_before, games_after)

    # Check anomalies_total
    b_total = before.get("anomalies_total", 0) / max(games_before, 1)
    c_total = after.get("anomalies_total", 0) / max(games_after, 1)
    total_delta = c_total - b_total

    if total_delta > 0.3:
        reasons.append(f"anomalies_total worsened: {b_total:.2f} -> {c_total:.2f} (+{total_delta:.2f}/g)")
        return _build_result(candidate_name, "reject", improved, worsened, safe, missing, reasons,
                            "Revert candidate. Anomalies increased.", games_before, games_after)

    # Check for clear improvement
    has_improvement = len(improved) > 0
    non_safety_worsened = [w for w in worsened if w["metric"] not in _SAFETY_METRICS]
    has_worsening = len(non_safety_worsened) > 0

    # Accept requires anomalies_total to improve (or at least not worsen)
    anomalies_improved = total_delta < -0.1

    # Check win_rate and p95 are not worsened
    wr_worsened = any(w["metric"] == "win_rate" for w in worsened)
    p95_worsened = any(w["metric"] == "p95_decision_time_ms" and abs(w["delta"]) > 50 for w in worsened)

    if has_improvement and not has_worsening and anomalies_improved:
        if wr_worsened:
            reasons.append("Improvement seen but win_rate worsened.")
            return _build_result(candidate_name, "hold", improved, worsened, safe, missing, reasons,
                                "Review win_rate regression.", games_before, games_after)
        reasons.append("Clear improvement with no worsening.")
        return _build_result(candidate_name, "accept", improved, worsened, safe, missing, reasons,
                            "Candidate is safe to adopt.", games_before, games_after)

    if has_improvement and has_worsening:
        all_minor = all(abs(w["delta"]) < 0.5 for w in non_safety_worsened)
        if anomalies_improved and all_minor and not wr_worsened and not p95_worsened:
            reasons.append(f"Net improvement ({total_delta:.2f}/g) with minor side effects.")
            return _build_result(candidate_name, "accept", improved, worsened, safe, missing, reasons,
                                "Candidate is safe to adopt. Monitor side effects.", games_before, games_after)
        if total_delta >= 0:
            reasons.append(f"anomalies_total did not improve ({total_delta:+.2f}/g) despite some metric changes.")
            return _build_result(candidate_name, "reject", improved, worsened, safe, missing, reasons,
                                "No net benefit. Revert candidate.", games_before, games_after)
        reasons.append("Mixed signals: improvement and worsening across metrics.")
        return _build_result(candidate_name, "hold", improved, worsened, safe, missing, reasons,
                            "Review manually. Consider additional validation.", games_before, games_after)

    if not has_improvement:
        if total_delta > 0:
            reasons.append("No improvement and anomalies increased.")
            return _build_result(candidate_name, "reject", improved, worsened, safe, missing, reasons,
                                "No benefit to adopt. Revert.", games_before, games_after)
        reasons.append("No clear improvement observed.")
        return _build_result(candidate_name, "hold", improved, worsened, safe, missing, reasons,
                            "No benefit to adopt. Keep current baseline.", games_before, games_after)

    return _build_result(candidate_name, "hold", improved, worsened, safe, missing, reasons,
                        "Inconclusive.", games_before, games_after)


def _build_result(candidate, decision, improved, worsened, safe, missing, reasons, next_action,
                  games_before, games_after):
    return {
        "candidate": candidate,
        "decision": decision,
        "games_before": games_before,
        "games_after": games_after,
        "improved_metrics": improved,
        "worsened_metrics": worsened,
        "safe_metrics": safe,
        "missing_metrics": missing,
        "reasons": reasons,
        "next_action": next_action,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_markdown(result: dict) -> str:
    lines = ["# Candidate Evaluation Report", ""]
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append(f"## Candidate: {result['candidate']}")
    lines.append("")
    lines.append(f"## Decision: **{result['decision']}**")
    lines.append("")
    lines.append(f"Games: {result['games_before']} (baseline) / {result['games_after']} (candidate)")
    lines.append("")

    if result["improved_metrics"]:
        lines.append("## Improved")
        lines.append("")
        for m in result["improved_metrics"]:
            lines.append(f"- {m['metric']}: {m['before']} -> {m['after']} ({m['delta']:+.4f})")
        lines.append("")

    if result["worsened_metrics"]:
        lines.append("## Worsened")
        lines.append("")
        for m in result["worsened_metrics"]:
            lines.append(f"- {m['metric']}: {m['before']} -> {m['after']} ({m['delta']:+.4f})")
        lines.append("")

    if result["missing_metrics"]:
        lines.append("## Missing Metrics")
        lines.append("")
        for m in result["missing_metrics"]:
            lines.append(f"- {m}")
        lines.append("")

    lines.append("## Reasons")
    lines.append("")
    for r in result["reasons"]:
        lines.append(f"- {r}")
    lines.append("")

    lines.append(f"## Next Action")
    lines.append("")
    lines.append(result["next_action"])
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Level 7-lite: Evaluate candidate")
    parser.add_argument("--before", required=True, help="Baseline anomaly report JSON")
    parser.add_argument("--after", required=True, help="Candidate anomaly report JSON")
    parser.add_argument("--candidate", default="unknown", help="Candidate name/description")
    parser.add_argument("--output", default="reports", help="Output directory")
    parser.add_argument("--min-games", type=int, default=20, help="Minimum games for evaluation")
    args = parser.parse_args()

    if not os.path.exists(args.before):
        print(f"Error: --before not found: {args.before}")
        sys.exit(1)
    if not os.path.exists(args.after):
        print(f"Error: --after not found: {args.after}")
        sys.exit(1)

    before = load_summary(args.before)
    after = load_summary(args.after)

    result = evaluate(before, after, args.candidate, args.min_games)

    md = generate_markdown(result)

    os.makedirs(args.output, exist_ok=True)
    json_path = os.path.join(args.output, "level7_candidate_evaluation.json")
    md_path = os.path.join(args.output, "level7_candidate_evaluation.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Candidate: {result['candidate']}")
    print(f"Decision:  {result['decision']}")
    print(f"Improved:  {len(result['improved_metrics'])}")
    print(f"Worsened:  {len(result['worsened_metrics'])}")
    print(f"Missing:   {len(result['missing_metrics'])}")
    for r in result["reasons"]:
        print(f"  - {r}")
    print(f"\nReports: {json_path}, {md_path}")


if __name__ == "__main__":
    main()
