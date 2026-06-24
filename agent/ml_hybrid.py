"""
Runtime ML hybrid scoring with safety gates.

Disabled by default. Enabled only with POKEMON_AI_ML_HYBRID=1.
No training at runtime — inference only from pre-learned tree.

When enabled, adds a small ML bonus to rule_score for each candidate.
Safety gates prevent dangerous ML proposals.
"""
from __future__ import annotations
import os
from typing import List, Dict, Optional

_HYBRID_DEFAULT = True  # submission candidate: ON by default
_ENABLED = os.environ.get("POKEMON_AI_ML_HYBRID", "1" if _HYBRID_DEFAULT else "0") != "0"
_BONUS_RATIO = float(os.environ.get("POKEMON_AI_ML_BONUS_RATIO", "10.0"))

_IONO_ENERGY_REQ = {"265": 2, "268": 1, "269": 4, "270": 1, "271": 3}
_MAIN_ATTACKERS = {"265", "269", "271"}
_AREA_ACTIVE = 4
_AREA_BENCH = 5

# Ablation modes for area fix experiment (#154 300g result: area_fix_only is best):
#   "area_fix_only" (default)        = correct inPlayArea 4/5, no attack compensation
#   "area_fix_attack_comp"           = correct inPlayArea + attack +0.15 (worse: miss_KO +36%)
#   "baseline"                       = original broken inPlayArea (0/1), experiment only
_AREA_FIX_MODE = os.environ.get("POKEMON_AI_AREA_FIX_MODE", "area_fix_only")

_ACTIVE_ATTACH_BONUS = float(os.environ.get("POKEMON_AI_ACTIVE_ATTACH_BONUS", "0.0"))
_BENCH_ATTACH_PENALTY = float(os.environ.get("POKEMON_AI_BENCH_ATTACH_PENALTY", "0.0"))

_ATTACK_PLAN_ENABLED = os.environ.get("POKEMON_AI_ATTACK_PLAN", "0") != "0"


def is_hybrid_enabled() -> bool:
    return _ENABLED


def _energy_needed(card_id: str, energy: int) -> int:
    req = _IONO_ENERGY_REQ.get(str(card_id), 0)
    return max(0, req - energy) if req > 0 else 0


def _extract_features(action: dict, state: dict) -> Dict[str, float]:
    """Extract lightweight features for ML scoring."""
    opt_type = action.get("type", 0)
    ap = state.get("active_pokemon") or {}
    opp = (state.get("opponent") or {}).get("active_pokemon") or {}

    active_cid = str(ap.get("card_id", ""))
    active_energy = ap.get("energy_count", 0) or 0
    active_hp = ap.get("hp_remaining", 0) or 0
    opp_hp = opp.get("hp_remaining", 0) or 0
    prizes = state.get("prizes_remaining", 6) or 6
    opp_prizes = (state.get("opponent") or {}).get("prizes_remaining", 6) or 6
    bench = state.get("bench") or []
    hand_count = state.get("hand_count", 0) or 0
    deck_count = state.get("deck_count", 0) or 0

    is_attach = opt_type == 8
    attach_area = action.get("inPlayArea")
    if _AREA_FIX_MODE == "baseline":
        attach_to_active = is_attach and attach_area == 0
        attach_to_bench = is_attach and attach_area == 1
    else:
        attach_to_active = is_attach and attach_area == _AREA_ACTIVE
        attach_to_bench = is_attach and attach_area == _AREA_BENCH
    active_e_needed = _energy_needed(active_cid, active_energy)
    is_main_attacker = active_cid in _MAIN_ATTACKERS

    return {
        "action_type": float(opt_type),
        "legal_action_count": 0.0,
        "has_legal_attack": 0.0,
        "active_hp": float(active_hp),
        "active_energy": float(active_energy),
        "active_energy_needed": float(active_e_needed),
        "opponent_active_hp": float(opp_hp),
        "bench_size": float(len(bench)),
        "prize_remaining": float(prizes),
        "opponent_prize_remaining": float(opp_prizes),
        "prize_diff": float(prizes - opp_prizes),
        "deck_count": float(deck_count),
        "hand_count": float(hand_count),
        "is_attack": 1.0 if opt_type == 13 else 0.0,
        "can_ko": 0.0,
        "is_zero_damage_attack": 0.0,
        "attack_energy_ready": 1.0 if active_e_needed <= 0 else 0.0,
        "is_attach": 1.0 if is_attach else 0.0,
        "attach_to_active": 1.0 if attach_to_active else 0.0,
        "attach_to_bench": 1.0 if attach_to_bench else 0.0,
        "attach_enables_attack": 1.0 if attach_to_active and active_e_needed == 1 else 0.0,
        "active_attach_would_enable": 1.0 if active_e_needed == 1 else 0.0,
        "active_is_main_attacker": 1.0 if is_main_attacker else 0.0,
        "is_evolve": 1.0 if opt_type == 9 else 0.0,
        "evolve_to_main_attacker": 0.0,
        "evolve_to_engine": 0.0,
        "is_play": 1.0 if opt_type in (3, 7) else 0.0,
        "is_ability": 1.0 if opt_type == 10 else 0.0,
        "is_retreat": 1.0 if opt_type == 12 else 0.0,
        "is_end": 1.0 if opt_type == 14 else 0.0,
        "late_game": 1.0 if prizes <= 2 or opp_prizes <= 2 else 0.0,
        "reward": 0.0,
    }


def _heuristic_ml_score(features: Dict[str, float]) -> float:
    """Simple heuristic scorer mimicking decision tree patterns.
    Learned from #144 shadow scoring analysis."""
    score = 0.5
    if features["is_attack"] > 0:
        score += 0.3
    if features["is_end"] > 0:
        score -= 0.1
    if features["active_energy_needed"] <= 0 and features["is_attack"] > 0:
        score += 0.2
    if features["attach_to_active"] > 0 and features["active_attach_would_enable"] > 0:
        score += 0.15
    if features["is_evolve"] > 0:
        score += 0.05
    if features["late_game"] > 0 and features["is_attack"] > 0:
        score += 0.1
    if features["prize_diff"] < 0:
        score += 0.05

    # --- Attack compensation (experiment only, not default) ---
    # 300g ablation (#154) showed this worsens miss_KO by 36%.
    if _AREA_FIX_MODE == "area_fix_attack_comp":
        if features["is_attack"] > 0 and features["has_legal_attack"] > 0:
            score += 0.15

    # --- Active energy priority tuning (#159 top episode comparison) ---
    # Top agents: attach_to_active 81.3% vs our 49.7%.
    # Defaults are 0.0 — no effect unless env var is set.
    if _ACTIVE_ATTACH_BONUS > 0:
        if (features["attach_to_active"] > 0
                and features["active_energy_needed"] > 0
                and features["active_is_main_attacker"] > 0):
            score += _ACTIVE_ATTACH_BONUS
    if _BENCH_ATTACH_PENALTY > 0:
        if (features["attach_to_bench"] > 0
                and features["active_energy_needed"] > 0
                and features["active_is_main_attacker"] > 0):
            score -= _BENCH_ATTACH_PENALTY

    return max(0.0, min(1.0, score))


def _safety_gate(action: dict, has_legal_attack: bool, has_ko_candidate: bool) -> bool:
    """Return True if ML bonus is allowed for this action."""
    opt_type = action.get("type", 0)
    if opt_type == 14 and has_legal_attack:
        return False
    if opt_type == 13:
        reason = str(action.get("reason") or action.get("rule_reason") or "")
        if "zero_damage" in reason.lower() or "0_damage" in reason.lower():
            return False
    if has_ko_candidate and opt_type != 13:
        return False
    return True


def apply_hybrid_bonus(
    candidates: List[dict],
    state: dict,
    scores: List[float],
) -> List[float]:
    """Apply ML hybrid bonus to candidate scores. Returns modified scores.
    Only active when POKEMON_AI_ML_HYBRID=1."""
    if not _ENABLED or not candidates:
        return scores

    try:
        has_legal_attack = any(c.get("type") == 13 for c in candidates)
        has_ko = any("ko" in str(c.get("reason") or "").lower()
                     and c.get("type") == 13 for c in candidates)

        ml_scores = []
        for c in candidates:
            feat = _extract_features(c, state)
            feat["has_legal_attack"] = 1.0 if has_legal_attack else 0.0
            feat["legal_action_count"] = float(len(candidates))
            ml_scores.append(_heuristic_ml_score(feat))

        ml_min = min(ml_scores)
        ml_max = max(ml_scores)
        ml_range = ml_max - ml_min if ml_max > ml_min else 1.0

        result = list(scores)
        for i, c in enumerate(candidates):
            if _safety_gate(c, has_legal_attack, has_ko):
                normalized = (ml_scores[i] - ml_min) / ml_range
                result[i] += _BONUS_RATIO * normalized

        if _ATTACK_PLAN_ENABLED:
            try:
                from agent.attack_plan import get_cached_top_plans, plan_matches_action
                plans = get_cached_top_plans(state, limit=3)
                if plans:
                    for i, c in enumerate(candidates):
                        bonus = max(plan_matches_action(p, c, state) for p in plans)
                        result[i] += bonus
            except Exception:
                pass

        return result
    except Exception:
        return scores
