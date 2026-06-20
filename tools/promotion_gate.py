"""
Promotion gate for staged weight tuning.

Decides whether a candidate should advance to the next evaluation stage
(30g->50g->200g) or receive a final accept/hold/reject decision.

Usage:
  python tools/promotion_gate.py --stage 30g \
      --baseline-apg 4.97 --candidate-apg 4.40 \
      --safety all_0

  python tools/promotion_gate.py --stage 200g \
      --baseline-apg 4.97 --candidate-apg 4.50 \
      --safety all_0 \
      --consistency 30g=-11,50g=-11,200g=-9.5 \
      --output reports/promotion_decision.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

_SAFETY_METRICS = {
    "attack_available_but_no_attack",
    "end_when_attack_available",
    "retreat_when_attack_available",
    "ability_without_followup_attack",
}

_CATEGORY_REGRESSION_THRESHOLD = 0.20


def evaluate_stage(
    stage: str,
    baseline_apg: float,
    candidate_apg: float,
    safety: str = "all_0",
    category_regressions: list = None,
    consistency: dict = None,
) -> dict:
    """Evaluate a candidate at a given stage.

    Args:
        stage: "30g", "50g", or "200g"
        baseline_apg: baseline anomalies per game
        candidate_apg: candidate anomalies per game
        safety: "all_0" or description of non-zero metrics
        category_regressions: list of {"category", "baseline", "candidate", "delta_pct"}
        consistency: dict of stage->improvement_pct for prior stages (200g only)

    Returns:
        dict with decision, promote, reasons, next_action, etc.
    """
    if category_regressions is None:
        category_regressions = []
    if consistency is None:
        consistency = {}

    safety_ok = safety == "all_0"
    delta = candidate_apg - baseline_apg
    improvement_pct = (delta / baseline_apg * 100) if baseline_apg > 0 else 0.0

    large_regressions = [
        r for r in category_regressions
        if abs(r.get("delta_pct", 0)) > _CATEGORY_REGRESSION_THRESHOLD * 100
    ]

    result = {
        "stage": stage,
        "baseline_anomalies_per_game": baseline_apg,
        "candidate_anomalies_per_game": candidate_apg,
        "delta": round(delta, 4),
        "improvement_percent": round(improvement_pct, 2),
        "safety_ok": safety_ok,
        "safety": safety,
        "category_regressions": large_regressions,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    if stage in ("30g", "50g"):
        result.update(_evaluate_promotion(stage, delta, baseline_apg, safety_ok, large_regressions))
    elif stage == "200g":
        result.update(_evaluate_final(
            delta, improvement_pct, safety_ok, large_regressions, consistency
        ))
    else:
        result["decision"] = "error"
        result["promote"] = False
        result["reason"] = f"Unknown stage: {stage}"
        result["next_action"] = "Fix stage parameter."

    return result


def _evaluate_promotion(
    stage: str, delta: float, baseline_apg: float, safety_ok: bool, large_regressions: list
) -> dict:
    next_stage = "50g" if stage == "30g" else "200g"

    if not safety_ok:
        return {
            "decision": "reject",
            "promote": False,
            "reason": "Safety metrics not all zero.",
            "next_action": "Reject candidate. Do not promote.",
        }

    if delta > 0:
        return {
            "decision": "no_promote",
            "promote": False,
            "reason": f"Candidate worse than baseline at {stage} (delta={delta:+.4f}).",
            "next_action": f"Do not promote to {next_stage}. Consider other candidates.",
        }

    if delta == 0:
        return {
            "decision": "no_promote",
            "promote": False,
            "reason": f"No improvement at {stage}.",
            "next_action": f"Do not promote to {next_stage}.",
        }

    if large_regressions:
        cats = ", ".join(r["category"] for r in large_regressions)
        return {
            "decision": "hold",
            "promote": False,
            "reason": f"Improved overall but large category regressions: {cats}.",
            "next_action": "Review category regressions before promoting.",
        }

    return {
        "decision": "promote",
        "promote": True,
        "reason": f"Improved at {stage} (delta={delta:+.4f}, {delta / baseline_apg * 100:+.1f}%). Safety OK.",
        "next_action": f"Promote to {next_stage} validation.",
    }


def _evaluate_final(
    delta: float,
    improvement_pct: float,
    safety_ok: bool,
    large_regressions: list,
    consistency: dict,
) -> dict:
    if not safety_ok:
        return {
            "decision": "reject",
            "promote": False,
            "reason": "Safety metrics not all zero at 200g.",
            "next_action": "Reject candidate.",
        }

    if delta > 0:
        return {
            "decision": "reject",
            "promote": False,
            "reason": f"Worse than baseline at 200g (delta={delta:+.4f}).",
            "next_action": "Reject candidate.",
        }

    if delta == 0:
        return {
            "decision": "hold",
            "promote": False,
            "reason": "No improvement at 200g.",
            "next_action": "Hold. No benefit to adopting.",
        }

    if abs(improvement_pct) < 2.0:
        return {
            "decision": "hold",
            "promote": False,
            "reason": f"Marginal improvement at 200g ({improvement_pct:+.2f}%).",
            "next_action": "Hold. Improvement too small to justify adoption.",
        }

    if large_regressions:
        cats = ", ".join(r["category"] for r in large_regressions)
        return {
            "decision": "hold",
            "promote": False,
            "reason": f"Improved overall but large category regressions: {cats}.",
            "next_action": "Hold. Review regressions before adopting.",
        }

    inconsistent = False
    if consistency:
        directions = [v < 0 for v in consistency.values()]
        inconsistent = not all(directions)

    if inconsistent:
        return {
            "decision": "hold",
            "promote": False,
            "reason": f"Inconsistent improvement across stages: {consistency}.",
            "next_action": "Hold. Improvement not stable across scales.",
        }

    return {
        "decision": "accept",
        "promote": False,
        "reason": f"Consistent improvement at 200g ({improvement_pct:+.2f}%). Safety OK.",
        "next_action": "Create adoption PR.",
    }


def main():
    parser = argparse.ArgumentParser(description="Promotion gate for weight tuning")
    parser.add_argument("--stage", required=True, choices=["30g", "50g", "200g"])
    parser.add_argument("--baseline-apg", type=float, required=True,
                        help="Baseline anomalies per game")
    parser.add_argument("--candidate-apg", type=float, required=True,
                        help="Candidate anomalies per game")
    parser.add_argument("--safety", default="all_0",
                        help="Safety status: 'all_0' or description")
    parser.add_argument("--category-regressions", default="",
                        help="Comma-sep 'cat:delta_pct' e.g. 'bb_correct:+15'")
    parser.add_argument("--consistency", default="",
                        help="Comma-sep 'stage=pct' e.g. '30g=-11,50g=-11,200g=-9.5'")
    parser.add_argument("--output", help="Output JSON path")

    args = parser.parse_args()

    regressions = []
    if args.category_regressions:
        for part in args.category_regressions.split(","):
            cat, pct = part.strip().split(":")
            regressions.append({"category": cat, "delta_pct": float(pct)})

    consistency = {}
    if args.consistency:
        for part in args.consistency.split(","):
            stage, pct = part.strip().split("=")
            consistency[stage] = float(pct)

    result = evaluate_stage(
        args.stage, args.baseline_apg, args.candidate_apg,
        args.safety, regressions, consistency,
    )

    print(json.dumps(result, indent=2))

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
