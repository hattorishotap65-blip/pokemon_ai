"""
ML feature extraction from state, action, and attack plan.

Produces flat dicts of numeric/boolean features for ML scoring.
All functions are safe for None/empty inputs.
"""
from __future__ import annotations
from typing import Any, Dict


def extract_state_features(state: dict) -> dict:
    if not isinstance(state, dict):
        return {}
    ap = state.get("active_pokemon") or {}
    opp = state.get("opponent") or {}
    opp_ap = opp.get("active_pokemon") or {}
    bench = state.get("bench") or []
    opp_bench = opp.get("bench") or []

    return {
        "turn": state.get("turn", 0) or 0,
        "prizes_remaining": state.get("prizes_remaining", 6) or 6,
        "opponent_prizes_remaining": opp.get("prizes_remaining", 6) or 6,
        "my_active_card_id": str(ap.get("card_id", "")),
        "my_active_hp": ap.get("hp_remaining", 0) or 0,
        "my_active_energy": ap.get("energy_count", 0) or 0,
        "my_active_is_ex": bool(ap.get("is_ex", False)),
        "opp_active_card_id": str(opp_ap.get("card_id", "")),
        "opp_active_hp": opp_ap.get("hp_remaining", 0) or 0,
        "opp_active_is_ex": bool(opp_ap.get("is_ex", False)),
        "bench_count": len([b for b in bench if isinstance(b, dict)]),
        "opp_bench_count": len([b for b in opp_bench if isinstance(b, dict)]),
        "deck_count": state.get("deck_count", 0) or 0,
        "hand_count": state.get("hand_count", 0) or 0,
    }


def extract_action_features(action: dict, state: dict) -> dict:
    if not isinstance(action, dict):
        return {}
    opt_type = action.get("type")
    return {
        "action_type": opt_type,
        "is_attack": opt_type == 13 and action.get("attackId") is not None,
        "is_ability": opt_type == 10,
        "is_retreat": opt_type == 12,
        "is_end": opt_type == 14,
        "is_play": opt_type == 7,
        "is_attach": opt_type == 8,
        "card_id": str(action.get("cardId") or action.get("resolved_card_id") or ""),
        "attack_id": action.get("attackId"),
    }


def extract_damage_features(action: dict, state: dict) -> dict:
    if not isinstance(state, dict):
        return {}
    try:
        from agent.damage_predictor import predict_attack_damage
        my_active = state.get("active_pokemon") or {}
        opp_active = (state.get("opponent") or {}).get("active_pokemon") or {}
        pred = predict_attack_damage(my_active, opp_active, state)
        return {
            "predicted_damage": pred.get("predicted_damage", 0),
            "raw_damage": pred.get("raw_damage", 0),
            "can_damage": pred.get("can_damage", False),
            "can_ko": pred.get("can_ko", False),
            "damage_prevented": pred.get("damage_prevented", False),
            "weakness_applies": pred.get("weakness_applies", False),
            "opp_active_hp": opp_active.get("hp_remaining", 0) or 0,
        }
    except Exception:
        return {}


def extract_plan_features(state: dict, action: dict) -> dict:
    try:
        from agent.attack_plan import get_cached_top_plans, plan_matches_action
        plans = get_cached_top_plans(state, limit=3)
        if not plans:
            return {"best_plan_type": "", "best_plan_score": 0, "top_plan_count": 0,
                    "action_matches_plan": False, "action_plan_bonus": 0.0}

        best = plans[0]
        bonus = max((plan_matches_action(p, action, state) for p in plans), default=0.0)

        return {
            "best_plan_type": best.plan_type,
            "best_plan_score": best.plan_score,
            "plan_can_ko": best.can_ko,
            "plan_wins_game": best.wins_game,
            "plan_needs_switch": best.needs_switch,
            "plan_needs_boss": best.needs_boss,
            "plan_needs_energy": best.needs_energy,
            "plan_needs_bellibolt_ability": best.needs_bellibolt_ability,
            "top_plan_count": len(plans),
            "action_matches_plan": bonus > 0,
            "action_plan_bonus": bonus,
        }
    except Exception:
        return {"best_plan_type": "", "best_plan_score": 0, "top_plan_count": 0,
                "action_matches_plan": False, "action_plan_bonus": 0.0}


def extract_features(state: dict, action: dict) -> dict:
    """Extract all features for ML scoring."""
    f = {}
    f.update(extract_state_features(state))
    f.update(extract_action_features(action, state))
    f.update(extract_damage_features(action, state))
    f.update(extract_plan_features(state, action))
    return f
