"""
Classify anomalies from Level 3 reports into actionable fix candidate groups.

Categories:
  real_fix_candidate        — agent behavior fix needed
  no_fix_needed             — current behavior is correct
  no_actionable_fix_game_flow — ideal differs but safe fix not available
  logging_insufficient      — cannot determine from available log data
  classifier_false_positive — detection logic error (should not reach here after F0005)

Special: best_damage_attacker_not_selected is subdivided by attacker,
damage range, and whether the gap has been proven unreachable by F0009/F0010.
"""
from __future__ import annotations
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# best_damage_attacker_not_selected sub-classification
# ---------------------------------------------------------------------------

# Ranges proven unreachable by F0009/F0010 A/B tests
_PIVOT_REJECTED_RANGES = {
    "bb_240_259": "F0009/F0010 rejected: BB 240-259 pivot causes downstream regressions",
    "kw_120_179": "F0009 rejected: KW 120-179 pivot has insufficient effect",
}


def _classify_best_damage(a: dict) -> str:
    """Sub-classify a best_damage_attacker_not_selected anomaly."""
    actual = str(a.get("actual_attacker") or a.get("active_id") or "")
    est_dmg = a.get("estimated_voltorb_damage")

    if actual == "270":
        # Wattrel: F0001 addressed via retreat bonus, remaining = game flow
        if est_dmg is not None and est_dmg >= 100:
            return "wt_game_flow_no_actionable_fix"
        return "unknown_due_to_missing_pivot_or_energy_info"

    if actual == "271":
        # KW >=180: F0007 pivot exists, remaining = game flow re-creation
        if est_dmg is not None and est_dmg >= 180:
            return "kw_f0007_range_game_flow_no_actionable_fix"
        # KW 120-179: F0009 rejected
        if est_dmg is not None and est_dmg >= 120:
            return "kw_120_179_no_actionable_fix"
        return "unknown_due_to_missing_pivot_or_energy_info"

    if actual == "269":
        # BB >=260: F0007 pivot exists, remaining = no retreat available
        if est_dmg is not None and est_dmg >= 260:
            return "bb_f0007_range_no_retreat_no_actionable_fix"
        # BB 240-259: F0009/F0010 rejected
        if est_dmg is not None and est_dmg > 230:
            return "bb_240_259_no_actionable_fix"
        return "bellibolt_attack_probably_correct"

    return "unknown_due_to_missing_pivot_or_energy_info"


# ---------------------------------------------------------------------------
# Action mapping
# ---------------------------------------------------------------------------

_SUGGESTED_ACTION = {
    # Actionable
    "voltorb_over_wattrel_missed":        "scoring_adjustment",
    "voltorb_over_kilowattrel_missed":    "scoring_adjustment",
    "bellibolt_over_voltorb_high_damage":  "scoring_adjustment",
    "attack_available_but_no_attack":      "scoring_adjustment",
    "end_when_attack_available":           "scoring_adjustment",
    "retreat_when_attack_available":       "scoring_adjustment",
    "ability_without_followup_attack":     "scoring_adjustment",
    "voltorb_scaling_attack_underused":    "scoring_adjustment",
    "ko_available_but_no_attack":          "scoring_adjustment",
    "ability_breaks_attack_ready_state":   "scoring_adjustment",
    "overattach_to_ready_attacker":        "profile_adjustment",
    "stronger_ready_bench_attacker_not_promoted": "scoring_adjustment",
    "stage1_without_base_search":          "detector_refinement",
    "duplicate_stage1_search":             "detector_refinement",
    # No fix needed
    "bellibolt_attack_probably_correct":   "no_fix_needed",
    # No actionable fix (proven by F0007/F0009/F0010 or game flow)
    "bb_240_259_no_actionable_fix":        "no_actionable_fix_game_flow",
    "kw_120_179_no_actionable_fix":        "no_actionable_fix_game_flow",
    "kw_f0007_range_game_flow_no_actionable_fix": "no_actionable_fix_game_flow",
    "bb_f0007_range_no_retreat_no_actionable_fix": "no_actionable_fix_game_flow",
    "wt_game_flow_no_actionable_fix":      "no_actionable_fix_game_flow",
    # Logging
    "unknown_due_to_missing_pivot_or_energy_info": "logging_improvement",
}

# Classifications excluded from fix prompt generation
_EXCLUDED_FROM_FIX_PROMPT = {
    "no_fix_needed",
    "no_actionable_fix_game_flow",
    "classifier_false_positive",
}


def classify_anomalies(anomalies: list[dict]) -> dict:
    """Classify anomalies into groups with action recommendations."""
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
    return "medium" if count >= 5 else "low"


def _risk_for(classification: str) -> str:
    if classification in ("bellibolt_over_voltorb_high_damage",
                          "voltorb_over_kilowattrel_missed"):
        return "medium"
    if classification == "voltorb_over_wattrel_missed":
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
        "bb_240_259_no_actionable_fix":
            "BB 240-259: pivot proven to cause regressions (F0009/F0010 rejected)",
        "kw_120_179_no_actionable_fix":
            "KW 120-179: pivot proven ineffective (F0009 rejected)",
        "kw_f0007_range_game_flow_no_actionable_fix":
            "KW >=180: F0007 pivot exists but game flow re-creates KW active turns",
        "bb_f0007_range_no_retreat_no_actionable_fix":
            "BB >=260: F0007 pivot exists but retreat option was not available",
        "wt_game_flow_no_actionable_fix":
            "Wattrel: F0001 addressed, remaining are game flow or retreat unavailable",
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
            "Attacker selection may underweight Voltorb scaling damage compared with Kilowattrel static priority.",
        "voltorb_over_wattrel_missed":
            "Wattrel should not be attacking when Voltorb has significantly higher damage potential.",
        "bellibolt_over_voltorb_high_damage":
            "Bellibolt ex is being used as primary attacker even when Voltorb scaling damage exceeds 230.",
        "bellibolt_attack_probably_correct":
            "Bellibolt ex attack is reasonable when its 230 damage equals or exceeds Voltorb estimate. No fix needed.",
        "bb_240_259_no_actionable_fix":
            "Voltorb 240-259 exceeds BB 230 but pivot causes downstream regressions. Proven by F0009/F0010.",
        "kw_120_179_no_actionable_fix":
            "Voltorb 120-179 exceeds KW 70 but pivot has insufficient effect. Proven by F0009.",
        "kw_f0007_range_game_flow_no_actionable_fix":
            "F0007 pivot exists for KW >=180 but game flow re-creates KW active turns. Not fixable by pivot.",
        "bb_f0007_range_no_retreat_no_actionable_fix":
            "F0007 pivot exists for BB >=260 but retreat option was unavailable. Not fixable by pivot.",
        "wt_game_flow_no_actionable_fix":
            "F0001 retreat bonus exists but Wattrel active recurs due to game flow. Not fixable by pivot.",
        "unknown_due_to_missing_pivot_or_energy_info":
            "Cannot determine if Voltorb was available. Log does not contain bench attacker readiness.",
        "attack_available_but_no_attack":
            "Turn ended without attacking despite a legal attack being available.",
        "end_when_attack_available":
            "End was selected over a legal attack.",
    }
    return causes.get(classification, f"Root cause for {classification} needs investigation.")


def _target_files_for(classification: str) -> list[str]:
    targets = {
        "voltorb_over_kilowattrel_missed": ["agent/ionos_rules.py", "agent/policy.py", "data/deck_profile.json"],
        "voltorb_over_wattrel_missed": ["agent/ionos_rules.py", "agent/policy.py"],
        "bellibolt_over_voltorb_high_damage": ["agent/ionos_rules.py", "agent/policy.py", "data/deck_profile.json"],
        "bellibolt_attack_probably_correct": [],
        "bb_240_259_no_actionable_fix": [],
        "kw_120_179_no_actionable_fix": [],
        "unknown_due_to_missing_pivot_or_energy_info": ["agent/logger.py", "main.py"],
        "attack_available_but_no_attack": ["agent/turn_rule_engine.py", "agent/policy.py", "agent/ionos_rules.py"],
        "end_when_attack_available": ["agent/turn_rule_engine.py", "agent/policy.py"],
        "retreat_when_attack_available": ["agent/ionos_rules.py", "agent/turn_rule_engine.py"],
        "overattach_to_ready_attacker": ["agent/ionos_rules.py", "data/deck_profile.json"],
        "voltorb_scaling_attack_underused": ["agent/ionos_rules.py", "data/deck_profile.json"],
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


def generate_fix_candidates(
    classification_result: dict,
    deck_profile_id: str = "unknown",
) -> list[dict]:
    """Generate fix candidates. Excludes no_fix_needed and no_actionable_fix."""
    global _CANDIDATE_COUNTER
    _CANDIDATE_COUNTER = 0

    groups  = classification_result["groups"]
    actions = classification_result["suggested_actions"]
    candidates = []

    priority_order = [
        "attack_available_but_no_attack",
        "end_when_attack_available",
        "ko_available_but_no_attack",
        "retreat_when_attack_available",
        "ability_without_followup_attack",
        "voltorb_scaling_attack_underused",
        "overattach_to_ready_attacker",
        "ability_breaks_attack_ready_state",
        "stage1_without_base_search",
        "duplicate_stage1_search",
        "stronger_ready_bench_attacker_not_promoted",
        "unknown_due_to_missing_pivot_or_energy_info",
        # Excluded: F0007 addressed or game flow or F0009/F0010 rejected
        "kw_f0007_range_game_flow_no_actionable_fix",
        "bb_f0007_range_no_retreat_no_actionable_fix",
        "wt_game_flow_no_actionable_fix",
        "bb_240_259_no_actionable_fix",
        "kw_120_179_no_actionable_fix",
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

        action = actions.get(key, "unknown")
        is_excluded = action in _EXCLUDED_FROM_FIX_PROMPT

        rep_ids = [a["id"] for a in group[:5]]
        actual_attackers = list(set(
            str(a.get("actual_attacker") or a.get("active_id") or "")
            for a in group
        ))
        dmg_values = [a.get("estimated_voltorb_damage") for a in group
                      if a.get("estimated_voltorb_damage")]
        dmg_range = [min(dmg_values), max(dmg_values)] if dmg_values else []

        priority = "excluded" if is_excluded else _priority_for(key, count, group)
        change_type = action

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
            "risk": _risk_for(key) if not is_excluded else "n/a",
            "expected_effect": _title_for(key),
            "do_not_change": ["deck.csv", "submission.tar.gz"],
            "requires_ab_test": change_type in ("scoring_adjustment", "profile_adjustment") and not is_excluded,
            "ab_test_metric": _ab_metrics_for(key) if not is_excluded else [],
            "excluded_from_fix_prompt": is_excluded,
        })

    return candidates
