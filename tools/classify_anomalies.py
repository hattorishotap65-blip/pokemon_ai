"""
Classify anomalies from Level 3 reports into actionable fix candidate groups.

Special focus: best_damage_attacker_not_selected is subdivided by attacker
and Voltorb estimated damage.
"""
from __future__ import annotations
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# best_damage_attacker_not_selected sub-classification
# ---------------------------------------------------------------------------

def _classify_best_damage(a: dict) -> str:
    """Sub-classify a best_damage_attacker_not_selected anomaly."""
    actual = str(a.get("actual_attacker") or a.get("active_id") or "")
    est_dmg = a.get("estimated_voltorb_damage") or 0

    if actual == "270":
        return "voltorb_over_wattrel_missed"
    if actual == "271":
        return "voltorb_over_kilowattrel_missed"
    if actual == "269":
        if est_dmg > 230:
            return "bellibolt_over_voltorb_high_damage"
        else:
            return "bellibolt_attack_probably_correct"
    return "unknown_due_to_missing_pivot_or_energy_info"


# ---------------------------------------------------------------------------
# General classification
# ---------------------------------------------------------------------------

_SUGGESTED_ACTION = {
    "voltorb_over_wattrel_missed":        "scoring_adjustment",
    "voltorb_over_kilowattrel_missed":    "scoring_adjustment",
    "bellibolt_over_voltorb_high_damage":  "scoring_adjustment",
    "bellibolt_attack_probably_correct":   "no_fix_needed",
    "unknown_due_to_missing_pivot_or_energy_info": "logging_improvement",
    "attack_available_but_no_attack":      "scoring_adjustment",
    "end_when_attack_available":           "scoring_adjustment",
    "retreat_when_attack_available":       "scoring_adjustment",
    "ability_without_followup_attack":     "scoring_adjustment",
    "voltorb_scaling_attack_underused":    "scoring_adjustment",
    "stage1_without_base_search":          "detector_refinement",
    "duplicate_stage1_search":             "detector_refinement",
    "overattach_to_ready_attacker":        "profile_adjustment",
    "ko_available_but_no_attack":          "scoring_adjustment",
    "ability_breaks_attack_ready_state":   "scoring_adjustment",
    "stronger_ready_bench_attacker_not_promoted": "scoring_adjustment",
}


def classify_anomalies(anomalies: list[dict]) -> dict:
    """
    Classify a list of anomalies into groups.

    Returns a dict:
      {
        "groups": { classification_key: [anomaly, ...] },
        "summary": { classification_key: count },
        "suggested_actions": { classification_key: action_type },
      }
    """
    groups: dict[str, list] = {}
    for a in anomalies:
        atype = a.get("type", "unknown")
        if atype == "best_damage_attacker_not_selected":
            key = _classify_best_damage(a)
        else:
            key = atype
        groups.setdefault(key, []).append(a)

    summary = {k: len(v) for k, v in groups.items()}
    actions = {k: _SUGGESTED_ACTION.get(k, "unknown") for k in groups}

    return {
        "groups": groups,
        "summary": summary,
        "suggested_actions": actions,
    }


# ---------------------------------------------------------------------------
# Fix candidate generation
# ---------------------------------------------------------------------------

_CANDIDATE_COUNTER = 0


def _next_fid() -> str:
    global _CANDIDATE_COUNTER
    _CANDIDATE_COUNTER += 1
    return f"F{_CANDIDATE_COUNTER:04d}"


def _priority_for(classification: str, count: int, anomalies: list[dict]) -> str:
    """Determine priority for a fix candidate group."""
    high_sev = sum(1 for a in anomalies if a.get("severity") in ("critical", "high"))
    if classification == "voltorb_over_wattrel_missed":
        return "high"
    if classification == "voltorb_over_kilowattrel_missed":
        return "high" if count >= 10 else "medium"
    if classification == "bellibolt_over_voltorb_high_damage":
        return "medium"
    if classification in ("attack_available_but_no_attack", "end_when_attack_available",
                          "ko_available_but_no_attack"):
        return "high" if high_sev > 0 else "medium"
    if classification in ("retreat_when_attack_available", "ability_breaks_attack_ready_state"):
        return "high" if count >= 5 else "medium"
    if classification in ("bellibolt_attack_probably_correct",
                          "unknown_due_to_missing_pivot_or_energy_info"):
        return "low"
    return "medium" if count >= 5 else "low"


def _risk_for(classification: str) -> str:
    if classification in ("bellibolt_over_voltorb_high_damage",
                          "voltorb_over_kilowattrel_missed"):
        return "medium"
    if classification == "voltorb_over_wattrel_missed":
        return "low"
    if classification in ("bellibolt_attack_probably_correct",
                          "unknown_due_to_missing_pivot_or_energy_info"):
        return "low"
    return "medium"


def _title_for(classification: str) -> str:
    titles = {
        "voltorb_over_kilowattrel_missed":
            "Prefer Voltorb scaling attack over Kilowattrel fixed 70 damage when Voltorb has high estimated damage",
        "voltorb_over_wattrel_missed":
            "Avoid attacking with Wattrel when Voltorb scaling damage is clearly superior",
        "bellibolt_over_voltorb_high_damage":
            "Consider Voltorb over Bellibolt ex when Voltorb estimated damage exceeds 230",
        "bellibolt_attack_probably_correct":
            "Bellibolt ex attack is likely correct (Voltorb damage <= 230)",
        "unknown_due_to_missing_pivot_or_energy_info":
            "Improve logging to determine if Voltorb was actually available as an attacker",
        "attack_available_but_no_attack":
            "Ensure attack is selected when a legal attack option exists",
        "end_when_attack_available":
            "Prevent End when a legal attack is available",
        "retreat_when_attack_available":
            "Prevent Retreat when a legal attack is available",
        "ability_without_followup_attack":
            "Ensure Ability usage is followed by attack when possible",
        "voltorb_scaling_attack_underused":
            "Increase Voltorb attack priority when scaling damage is high",
        "ko_available_but_no_attack":
            "Ensure KO opportunity is not missed",
        "overattach_to_ready_attacker":
            "Reduce energy over-attachment to already-ready attackers",
    }
    return titles.get(classification, f"Address {classification}")


def _root_cause_for(classification: str) -> str:
    causes = {
        "voltorb_over_kilowattrel_missed":
            "Attacker selection may underweight Voltorb scaling damage compared with Kilowattrel static priority. "
            "Agent does not consider retreating to Voltorb when Voltorb has higher expected damage.",
        "voltorb_over_wattrel_missed":
            "Wattrel should not be attacking when Voltorb has significantly higher damage potential.",
        "bellibolt_over_voltorb_high_damage":
            "Bellibolt ex is being used as primary attacker even when Voltorb scaling damage exceeds 230. "
            "Non-ex Voltorb would be more prize-efficient.",
        "bellibolt_attack_probably_correct":
            "Bellibolt ex attack is reasonable when its 230 damage equals or exceeds Voltorb estimate. No fix needed.",
        "unknown_due_to_missing_pivot_or_energy_info":
            "Cannot determine if Voltorb was available. Log does not contain bench attacker readiness.",
        "attack_available_but_no_attack":
            "Turn ended without attacking despite a legal attack being available in the select options.",
        "end_when_attack_available":
            "End was selected over a legal attack. turn_rule_engine or policy scoring may be insufficient.",
    }
    return causes.get(classification, f"Root cause for {classification} needs investigation.")


def _target_files_for(classification: str) -> list[str]:
    targets = {
        "voltorb_over_kilowattrel_missed": ["ionos_rules.py", "policy.py", "data/deck_profile.json"],
        "voltorb_over_wattrel_missed": ["ionos_rules.py", "policy.py"],
        "bellibolt_over_voltorb_high_damage": ["ionos_rules.py", "policy.py", "data/deck_profile.json"],
        "bellibolt_attack_probably_correct": [],
        "unknown_due_to_missing_pivot_or_energy_info": ["agent/logger.py", "main.py"],
        "attack_available_but_no_attack": ["turn_rule_engine.py", "policy.py", "ionos_rules.py"],
        "end_when_attack_available": ["turn_rule_engine.py", "policy.py"],
        "retreat_when_attack_available": ["ionos_rules.py", "turn_rule_engine.py"],
        "overattach_to_ready_attacker": ["ionos_rules.py", "data/deck_profile.json"],
        "voltorb_scaling_attack_underused": ["ionos_rules.py", "data/deck_profile.json"],
    }
    return targets.get(classification, ["tools/detect_anomalies.py"])


def _ab_metrics_for(classification: str) -> list[str]:
    base = ["win_rate"]
    specific = {
        "voltorb_over_kilowattrel_missed": ["voltorb_attack_count", "best_damage_attacker_not_selected"],
        "voltorb_over_wattrel_missed": ["voltorb_attack_count", "best_damage_attacker_not_selected"],
        "bellibolt_over_voltorb_high_damage": ["voltorb_attack_count", "best_damage_attacker_not_selected"],
        "attack_available_but_no_attack": ["attack_available_but_no_attack"],
        "end_when_attack_available": ["end_when_attack_available"],
    }
    return base + specific.get(classification, [])


def _change_type_for(classification: str) -> str:
    return _SUGGESTED_ACTION.get(classification, "unknown")


def generate_fix_candidates(
    classification_result: dict,
    deck_profile_id: str = "unknown",
) -> list[dict]:
    """Generate fix candidate entries from classification result."""
    global _CANDIDATE_COUNTER
    _CANDIDATE_COUNTER = 0

    groups   = classification_result["groups"]
    actions  = classification_result["suggested_actions"]
    candidates = []

    # Sort by priority order
    priority_order = [
        "voltorb_over_wattrel_missed",
        "voltorb_over_kilowattrel_missed",
        "attack_available_but_no_attack",
        "end_when_attack_available",
        "ko_available_but_no_attack",
        "retreat_when_attack_available",
        "ability_without_followup_attack",
        "voltorb_scaling_attack_underused",
        "bellibolt_over_voltorb_high_damage",
        "overattach_to_ready_attacker",
        "ability_breaks_attack_ready_state",
        "stage1_without_base_search",
        "duplicate_stage1_search",
        "stronger_ready_bench_attacker_not_promoted",
        "unknown_due_to_missing_pivot_or_energy_info",
        "bellibolt_attack_probably_correct",
    ]
    sorted_keys = sorted(groups.keys(), key=lambda k: (
        priority_order.index(k) if k in priority_order else 999
    ))

    for key in sorted_keys:
        group = groups[key]
        count = len(group)
        if count == 0:
            continue

        rep_ids = [a["id"] for a in group[:5]]
        actual_attackers = list(set(
            str(a.get("actual_attacker") or a.get("active_id") or "")
            for a in group
        ))
        dmg_values = [a.get("estimated_voltorb_damage") for a in group
                      if a.get("estimated_voltorb_damage")]
        dmg_range = [min(dmg_values), max(dmg_values)] if dmg_values else []

        priority = _priority_for(key, count, group)
        change_type = _change_type_for(key)

        candidates.append({
            "id": _next_fid(),
            "priority": priority,
            "source_anomaly_type": group[0].get("type", "unknown"),
            "classification": key,
            "title": _title_for(key),
            "root_cause_hypothesis": _root_cause_for(key),
            "evidence": {
                "count": count,
                "representative_anomaly_ids": rep_ids,
                "actual_attackers": actual_attackers,
                "estimated_voltorb_damage_range": dmg_range,
            },
            "suggested_change_type": change_type,
            "suggested_target_files": _target_files_for(key),
            "risk": _risk_for(key),
            "expected_effect": _title_for(key),
            "do_not_change": ["deck.csv", "submission.tar.gz"],
            "requires_ab_test": change_type in ("scoring_adjustment", "profile_adjustment"),
            "ab_test_metric": _ab_metrics_for(key),
        })

    return candidates
