"""
Lightweight attack plan generator.

Produces ranked attack plans for the current turn based on visible
board state. Plans are advisory — policy uses them as score bonuses,
not absolute commands.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_VOLTORB = "265"
_BELLIBOLT_EX = "269"
_KILOWATTREL = "271"
_VOLTORB_ENERGY_REQ = 2
_BELLIBOLT_ENERGY_REQ = 4
_KILOWATTREL_ENERGY_REQ = 3


@dataclass
class AttackPlan:
    plan_type: str
    attacker_cid: str = ""
    attacker_name: str = ""
    target_cid: str = ""
    target_name: str = ""
    attack_index: int = 0
    predicted_damage: int = 0
    can_ko: bool = False
    wins_game: bool = False
    needs_switch: bool = False
    needs_boss: bool = False
    needs_bellibolt_ability: bool = False
    needs_energy: bool = False
    plan_score: float = 0.0
    reasons: list = field(default_factory=list)


def _bellibolt_on_field(state: dict) -> bool:
    active_cid = str((state.get("active_pokemon") or {}).get("card_id", ""))
    if active_cid == _BELLIBOLT_EX:
        return True
    for b in (state.get("bench") or []):
        if str(b.get("card_id", "")) == _BELLIBOLT_EX:
            return True
    return False


def generate_attack_plans(state: dict) -> List[AttackPlan]:
    """Generate candidate attack plans from current board state."""
    plans: List[AttackPlan] = []
    if not isinstance(state, dict):
        return plans

    my_active = state.get("active_pokemon") or {}
    opp_active = state.get("opponent", {}).get("active_pokemon") or {}
    opp_bench = state.get("opponent", {}).get("bench") or []
    my_bench = state.get("bench") or []
    my_prizes = int(state.get("prizes_remaining", 6) or 6)

    try:
        from agent.damage_predictor import predict_attack_damage
    except ImportError:
        return plans

    # --- 1. Active attacks opponent active ---
    if my_active:
        pred = predict_attack_damage(my_active, opp_active, state)
        if pred["can_damage"]:
            p = AttackPlan(
                plan_type="winning_ko" if _attack_wins(pred, my_prizes, opp_active) else "active_ko" if pred["can_ko"] else "active_attack",
                attacker_cid=str(my_active.get("card_id", "")),
                attacker_name=my_active.get("name", ""),
                target_cid=str(opp_active.get("card_id", "")),
                target_name=opp_active.get("name", ""),
                predicted_damage=pred["predicted_damage"],
                can_ko=pred["can_ko"],
                wins_game=_attack_wins(pred, my_prizes, opp_active),
                plan_score=_score_plan(pred, my_prizes, opp_active, is_active=True),
                reasons=pred.get("tags", []),
            )
            plans.append(p)

    # --- 2. Zero damage escape ---
    if my_active:
        active_pred = predict_attack_damage(my_active, opp_active, state)
        if active_pred["predicted_damage"] == 0 and active_pred["raw_damage"] > 0:
            for i, bench_mon in enumerate(my_bench):
                if not isinstance(bench_mon, dict):
                    continue
                bp = predict_attack_damage(bench_mon, opp_active, state)
                if bp["can_damage"]:
                    p = AttackPlan(
                        plan_type="zero_damage_escape",
                        attacker_cid=str(bench_mon.get("card_id", "")),
                        attacker_name=bench_mon.get("name", ""),
                        target_cid=str(opp_active.get("card_id", "")),
                        predicted_damage=bp["predicted_damage"],
                        can_ko=bp["can_ko"],
                        needs_switch=True,
                        plan_score=_score_plan(bp, my_prizes, opp_active, is_active=False, is_escape=True),
                        reasons=["zero_damage_escape"] + bp.get("tags", []),
                    )
                    plans.append(p)

    # --- 3. Boss KO targets ---
    for i, opp_mon in enumerate(opp_bench):
        if not isinstance(opp_mon, dict):
            continue
        pred = predict_attack_damage(my_active, opp_mon, state)
        if pred["can_ko"]:
            is_ex = opp_mon.get("is_ex", False)
            p = AttackPlan(
                plan_type="boss_ko",
                attacker_cid=str(my_active.get("card_id", "")),
                target_cid=str(opp_mon.get("card_id", "")),
                target_name=opp_mon.get("name", ""),
                predicted_damage=pred["predicted_damage"],
                can_ko=True,
                wins_game=_boss_wins(my_prizes, is_ex),
                needs_boss=True,
                plan_score=_score_boss_plan(pred, my_prizes, opp_mon),
                reasons=["boss_ko"] + (["boss_ko_ex"] if is_ex else []),
            )
            plans.append(p)

    # --- 4. Iono deck-specific plans ---
    all_mons = []
    if my_active:
        all_mons.append((my_active, True))
    for bm in my_bench:
        if isinstance(bm, dict):
            all_mons.append((bm, False))

    for mon, is_active in all_mons:
        cid = str(mon.get("card_id", ""))
        energy = mon.get("energy_count", 0) or 0
        bp = predict_attack_damage(mon, opp_active, state)

        if cid == _VOLTORB:
            needs_e = energy < _VOLTORB_ENERGY_REQ
            needs_bb = needs_e and _bellibolt_on_field(state)
            if bp["can_damage"] or needs_e:
                plans.append(AttackPlan(
                    plan_type="voltorb_charge",
                    attacker_cid=cid, attacker_name=mon.get("name", ""),
                    target_cid=str(opp_active.get("card_id", "")),
                    predicted_damage=bp["predicted_damage"],
                    can_ko=bp["can_ko"],
                    needs_switch=not is_active,
                    needs_energy=needs_e,
                    needs_bellibolt_ability=needs_bb,
                    plan_score=_score_plan(bp, my_prizes, opp_active, is_active) * (0.6 if needs_e else 1.0) + (30 if needs_bb else 0),
                    reasons=["voltorb_charge"] + (["needs_bellibolt"] if needs_bb else []),
                ))

        elif cid == _BELLIBOLT_EX:
            needs_e = energy < _BELLIBOLT_ENERGY_REQ
            one_away = energy == _BELLIBOLT_ENERGY_REQ - 1
            if one_away or (bp["can_damage"] and not needs_e):
                plans.append(AttackPlan(
                    plan_type="bellibolt_self_attack",
                    attacker_cid=cid, attacker_name=mon.get("name", ""),
                    target_cid=str(opp_active.get("card_id", "")),
                    predicted_damage=bp["predicted_damage"],
                    can_ko=bp["can_ko"],
                    needs_switch=not is_active,
                    needs_energy=needs_e,
                    needs_bellibolt_ability=one_away,
                    plan_score=_score_plan(bp, my_prizes, opp_active, is_active) * (0.7 if one_away else 1.0) + (40 if one_away else 0),
                    reasons=["bellibolt_self_attack"] + (["needs_bellibolt_ability"] if one_away else []),
                ))

        elif cid == _KILOWATTREL:
            needs_e = energy < _KILOWATTREL_ENERGY_REQ
            needs_bb = needs_e and _bellibolt_on_field(state)
            if bp["can_damage"]:
                plans.append(AttackPlan(
                    plan_type="kilowattrel_sub_attacker",
                    attacker_cid=cid, attacker_name=mon.get("name", ""),
                    target_cid=str(opp_active.get("card_id", "")),
                    predicted_damage=bp["predicted_damage"],
                    can_ko=bp["can_ko"],
                    needs_switch=not is_active,
                    needs_energy=needs_e,
                    needs_bellibolt_ability=needs_bb,
                    plan_score=_score_plan(bp, my_prizes, opp_active, is_active, is_escape=False) * (0.5 if needs_e else 1.0),
                    reasons=["kilowattrel_sub"] + (["needs_bellibolt"] if needs_bb else []),
                ))

        elif bp["can_damage"] and bp["predicted_damage"] > 0 and not is_active:
            plans.append(AttackPlan(
                plan_type="bench_attacker",
                attacker_cid=cid, attacker_name=mon.get("name", ""),
                target_cid=str(opp_active.get("card_id", "")),
                predicted_damage=bp["predicted_damage"],
                can_ko=bp["can_ko"],
                needs_switch=True,
                needs_energy=energy < 1,
                plan_score=_score_plan(bp, my_prizes, opp_active, is_active=False) * (0.5 if energy < 1 else 1.0),
                reasons=["bench_attacker"],
            ))

    plans.sort(key=lambda p: p.plan_score, reverse=True)
    return plans


def select_best_plan(state: dict) -> Optional[AttackPlan]:
    plans = generate_attack_plans(state)
    return plans[0] if plans else None


def select_top_plans(state: dict, limit: int = 3) -> List[AttackPlan]:
    plans = generate_attack_plans(state)
    return plans[:limit]


# ---------------------------------------------------------------------------
# Lightweight cache: reuse plans within the same state object's action loop
# ---------------------------------------------------------------------------

_cache_key = None
_cache_plans: List[AttackPlan] = []


def _make_cache_key(state: dict):
    """Fast cache key from state identity + core fields."""
    if not isinstance(state, dict):
        return None
    ap = state.get("active_pokemon") or {}
    opp = (state.get("opponent") or {}).get("active_pokemon") or {}
    return (
        id(state),
        str(ap.get("card_id", "")),
        ap.get("hp_remaining", 0),
        ap.get("energy_count", 0),
        str(opp.get("card_id", "")),
        opp.get("hp_remaining", 0),
        state.get("prizes_remaining", 6),
    )


def get_cached_top_plans(state: dict, limit: int = 3) -> List[AttackPlan]:
    """Return cached top plans if state hasn't changed, else regenerate."""
    global _cache_key, _cache_plans
    key = _make_cache_key(state)
    if key is not None and key == _cache_key:
        return _cache_plans[:limit]
    plans = generate_attack_plans(state)
    _cache_key = key
    _cache_plans = plans
    return plans[:limit]


def clear_attack_plan_cache():
    """Clear the plan cache (e.g. between turns)."""
    global _cache_key, _cache_plans
    _cache_key = None
    _cache_plans = []


def _attack_wins(pred: dict, my_prizes: int, opp: dict) -> bool:
    if not pred["can_ko"]:
        return False
    prizes_on_ko = 2 if opp.get("is_ex", False) else 1
    return my_prizes <= prizes_on_ko


def _boss_wins(my_prizes: int, is_ex: bool) -> bool:
    prizes_on_ko = 2 if is_ex else 1
    return my_prizes <= prizes_on_ko


def _score_plan(pred: dict, my_prizes: int, opp: dict,
                is_active: bool = True, is_escape: bool = False) -> float:
    score = 0.0
    if _attack_wins(pred, my_prizes, opp):
        score += 1000.0
    elif pred["can_ko"]:
        score += 200.0
        if opp.get("is_ex", False):
            score += 100.0
    else:
        score += min(pred["predicted_damage"] * 0.5, 100.0)
    if is_active:
        score += 50.0
    if is_escape:
        score += 150.0
    return score


def _score_boss_plan(pred: dict, my_prizes: int, opp_mon: dict) -> float:
    score = 100.0
    if _boss_wins(my_prizes, opp_mon.get("is_ex", False)):
        score += 500.0
    if opp_mon.get("is_ex", False):
        score += 80.0
    hp = opp_mon.get("hp_remaining", 9999) or 9999
    if hp <= 60:
        score += 50.0
    return score


def plan_matches_action(plan: AttackPlan, action: dict, state: dict) -> float:
    """Return bonus score if action aligns with the plan."""
    if plan is None:
        return 0.0
    opt_type = action.get("type")
    cid = str(action.get("cardId") or action.get("resolved_card_id") or "")

    # Attack matches plan's attacker
    if opt_type == 13 and plan.attacker_cid == str(state.get("active_pokemon", {}).get("card_id", "")):
        if not plan.needs_switch and not plan.needs_boss:
            return min(plan.plan_score * 0.05, 15.0)

    # Boss matches plan target
    if plan.needs_boss and opt_type in (3, 4):
        p_idx = action.get("playerIndex")
        my_idx = state.get("your_index", 0)
        if p_idx is not None and int(p_idx) != my_idx:
            area = action.get("area")
            idx = action.get("index")
            if area == 5 and idx is not None:
                opp_bench = state.get("opponent", {}).get("bench", [])
                if idx < len(opp_bench):
                    target_cid = str(opp_bench[idx].get("card_id", ""))
                    if target_cid == plan.target_cid:
                        return min(plan.plan_score * 0.05, 15.0)

    # Switch/Retreat matches plan attacker
    if plan.needs_switch and opt_type == 12:
        return min(plan.plan_score * 0.03, 8.0)

    # Bellibolt ability for plan
    if plan.needs_bellibolt_ability and opt_type == 10:
        return min(plan.plan_score * 0.02, 5.0)

    return 0.0
