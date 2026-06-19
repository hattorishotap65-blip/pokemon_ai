"""
Crustle-deck specific scoring bonuses.

Win condition: Dwebble → Crustle → Superb Scissors loop.
Teal Mask Ogerpon ex accelerates energy via Teal Dance ability.

score_bonus(action, state) returns (bonus: float, reason: str).
Return (0.0, "") when no Crustle-specific logic applies.
"""

# ── Card IDs ──────────────────────────────────────────────────
_DWEBBLE  = "344"
_CRUSTLE  = "345"
_OGERPON  = "96"     # Teal Mask Ogerpon ex — Teal Dance energy accel + Bianca enabler
_REGIROCK = "447"    # Sub-attacker

# Trainers that are always relevant for this archetype
_BUDDYS_POFFIN   = "1086"   # Buddy-Buddy Poffin — search 2 basics
_HERO_CAPE       = "1159"   # Hero's Cape — HP boost tool
_COOK            = "1212"   # Cook — heal active
_JUMBO_ICE_CREAM = "1147"   # Jumbo Ice Cream — heavy heal (3+ energy required)
_LILLIES         = "1227"   # Lillie's Determination — hand refresh
_WAITRESS        = "1235"   # Waitress — Grass Energy accel
_ERI             = "1186"   # Eri — recover basic energy from discard
_NIGHT_STRETCHER = "1097"   # Night Stretcher — recover pokemon/energy
_ENERGY_SWITCH   = "1116"   # Energy Switch — move energy to Crustle
_BOSS_ORDERS     = "1182"   # Boss's Orders — gust
_BIANCAS         = "1190"   # Bianca's Devotion — mass draw (needs Ogerpon)
_ULTRA_BALL      = "1121"   # Ultra Ball — universal search

_CRUSTLE_ENERGY_GOAL = 3    # Superb Scissors costs 3 energy

# AreaType ints (mirrors cg/api.py)
_AREA_ACTIVE = 4
_AREA_BENCH  = 5


# ── State helpers ──────────────────────────────────────────────

def _active_cid(state: dict) -> str:
    return str(state.get("active_pokemon", {}).get("card_id", ""))


def _active_energy(state: dict) -> int:
    return state.get("active_pokemon", {}).get("energy_count", 0)


def _active_hp_ratio(state: dict) -> float:
    a = state.get("active_pokemon", {})
    mx = a.get("max_hp", 1) or 1
    return a.get("hp_remaining", mx) / mx


def _bench_cids(state: dict) -> list[str]:
    return [str(p.get("card_id", "")) for p in state.get("bench", [])]


def _crustle_active(state: dict) -> bool:
    return _active_cid(state) == _CRUSTLE


def _crustle_on_field(state: dict) -> bool:
    return _CRUSTLE in _bench_cids(state) or _crustle_active(state)


def _dwebble_on_field(state: dict) -> bool:
    return _DWEBBLE in _bench_cids(state) or _active_cid(state) == _DWEBBLE


def _ogerpon_on_bench(state: dict) -> bool:
    return _OGERPON in _bench_cids(state)


def _opp_is_ex(state: dict) -> bool:
    """True when the opponent's active Pokemon is an ex (worth 2 prizes if KO'd)."""
    opp_cid = str(state.get("opponent", {}).get("active_pokemon", {}).get("card_id", ""))
    # We don't have card_table here, so use a heuristic: ex cards tend to be high-ID;
    # the knowledge module tags them. We'll keep it simple: return False by default
    # and let policy.py handle ex-awareness.
    return False   # Extended by callers that pass knowledge


# ── Main entry point ───────────────────────────────────────────

def score_bonus(action: dict, state: dict, knowledge=None) -> tuple[float, str]:
    """
    Return (bonus, reason) for Crustle-deck specific actions.
    bonus is ADDED to the base policy score.
    knowledge is an optional CardKnowledge instance for ex-tag checks.
    """
    opt_type = action.get("type")
    # Prefer resolved card ID over raw cardId
    cid = str(action.get("resolved_card_id") or action.get("cardId") or "")
    ctx = action.get("select_context")

    # ── 1. Evolve Dwebble → Crustle (top priority) ─────────────
    if opt_type == 9 and cid == _CRUSTLE:
        return 10.0, "crustle:evolve_crustle"

    # ── 2. Play Dwebble (evolution base) ────────────────────────
    if opt_type == 7 and cid == _DWEBBLE:
        bench = state.get("bench", [])
        if len(bench) < 5:
            extra = 0.0 if _crustle_on_field(state) else 2.0
            return 5.0 + extra, "crustle:play_dwebble"

    # ── 3. Play Teal Mask Ogerpon ex (enables Bianca + Teal Dance) ──
    if opt_type == 7 and cid == _OGERPON:
        if not _ogerpon_on_bench(state):
            return 4.0, "crustle:play_ogerpon"

    # ── 4. Attach energy to active Crustle ──────────────────────
    if opt_type == 8 and _crustle_active(state):
        in_play_area = action.get("inPlayArea")
        if in_play_area is None or in_play_area == _AREA_ACTIVE:
            shortage = _CRUSTLE_ENERGY_GOAL - _active_energy(state)
            bonus    = 5.0 if shortage > 0 else 1.0
            return bonus, "crustle:energy_to_active_crustle"

    # ── 5. Attach energy to benched Crustle ─────────────────────
    if opt_type == 8:
        in_play_area = action.get("inPlayArea")
        in_play_idx  = action.get("inPlayIndex")
        if in_play_area == _AREA_BENCH and in_play_idx is not None:
            bench = state.get("bench", [])
            if in_play_idx < len(bench):
                if str(bench[in_play_idx].get("card_id", "")) == _CRUSTLE:
                    return 3.0, "crustle:energy_to_bench_crustle"

    # ── 6. Ogerpon ability (Teal Dance) — extra energy attach ───
    if opt_type == 10 and cid == _OGERPON:
        # If Crustle needs more energy, Teal Dance is very valuable
        if _crustle_active(state) and _active_energy(state) < _CRUSTLE_ENERGY_GOAL:
            return 4.0, "crustle:teal_dance_for_crustle"
        return 2.0, "crustle:teal_dance"

    # ── 7. Attack with Crustle (Superb Scissors) ────────────────
    if opt_type == 13 and _crustle_active(state):
        energy = _active_energy(state)
        if energy >= _CRUSTLE_ENERGY_GOAL:
            # Extra bonus vs ex (Crustle is hard to KO; staying active is correct)
            opp_is_ex = _check_opp_ex(state, knowledge)
            ex_bonus  = 3.0 if opp_is_ex else 0.0
            return 5.0 + ex_bonus, "crustle:superb_scissors"

    # ── 8. Healing cards for damaged Crustle ────────────────────
    if opt_type == 7 and cid in (_COOK, _JUMBO_ICE_CREAM):
        if _crustle_active(state):
            dmg_ratio = 1.0 - _active_hp_ratio(state)
            if dmg_ratio >= 0.4:     # taken 40%+ damage → worth healing
                bonus = 5.0 if dmg_ratio >= 0.6 else 3.0
                return bonus, "crustle:heal_crustle"

    # ── 9. Hero's Cape on Crustle (tool attach context) ─────────
    if opt_type == 8 and cid == _HERO_CAPE:
        in_play_area = action.get("inPlayArea")
        in_play_idx  = action.get("inPlayIndex")
        if in_play_area == _AREA_ACTIVE and _crustle_active(state):
            return 6.0, "crustle:heroes_cape_active"
        if in_play_area == _AREA_BENCH and in_play_idx is not None:
            bench = state.get("bench", [])
            if in_play_idx < len(bench):
                if str(bench[in_play_idx].get("card_id", "")) == _CRUSTLE:
                    return 5.0, "crustle:heroes_cape_bench"

    # ── 10. ATTACH_FROM (ctx=21): picking which Pokemon gets the card ──
    if opt_type == 3 and ctx == 21:  # CARD + ATTACH_FROM context
        area    = action.get("area")
        idx_val = action.get("index")
        if area == _AREA_ACTIVE and _crustle_active(state):
            return 3.0, "crustle:attach_to_crustle_active"
        if area == _AREA_BENCH and idx_val is not None:
            bench = state.get("bench", [])
            if idx_val < len(bench):
                if str(bench[idx_val].get("card_id", "")) == _CRUSTLE:
                    return 2.0, "crustle:attach_to_crustle_bench"

    # ── 11. Energy Switch — move energy toward active Crustle ────
    if opt_type == 7 and cid == _ENERGY_SWITCH:
        if _crustle_active(state) and _active_energy(state) < _CRUSTLE_ENERGY_GOAL:
            return 3.0, "crustle:energy_switch_to_crustle"

    # ── 12. Eri — recover Fighting Energy from discard ──────────
    if opt_type == 7 and cid == _ERI:
        return 2.0, "crustle:eri_energy_recovery"

    # ── 13. Boss's Orders when close to winning ─────────────────
    if opt_type == 7 and cid == _BOSS_ORDERS:
        opp_prizes = state.get("opponent", {}).get("prizes_remaining", 6)
        if opp_prizes <= 2 and _crustle_active(state) and _active_energy(state) >= _CRUSTLE_ENERGY_GOAL:
            return 4.0, "crustle:boss_for_ko"

    # ── 14. Buddy-Buddy Poffin — get Dwebble ────────────────────
    if opt_type == 7 and cid == _BUDDYS_POFFIN:
        if not _dwebble_on_field(state):
            return 4.0, "crustle:poffin_fetch_dwebble"

    # ── 15. TO_HAND context — prefer Crustle chain cards ────────
    if ctx == 7:   # SelectContext.TO_HAND
        if cid == _CRUSTLE:
            return 4.0, "crustle:search_crustle"
        if cid == _DWEBBLE and not _dwebble_on_field(state):
            return 3.0, "crustle:search_dwebble"
        if cid == _OGERPON and not _ogerpon_on_bench(state):
            return 2.0, "crustle:search_ogerpon"

    # ── 16. Bianca's Devotion when Ogerpon is present ───────────
    if opt_type == 7 and cid == _BIANCAS:
        if _ogerpon_on_bench(state):
            hand_count = state.get("hand_count", 5)
            if hand_count <= 4:
                return 3.0, "crustle:biancas_with_ogerpon"

    # ── 17. Night Stretcher — recover Crustle or energy ─────────
    if opt_type == 7 and cid == _NIGHT_STRETCHER:
        return 1.5, "crustle:night_stretcher"

    return 0.0, ""


def _check_opp_ex(state: dict, knowledge) -> bool:
    """Check if opponent's active is an ex Pokemon using card knowledge."""
    try:
        opp_cid = str(state.get("opponent", {}).get("active_pokemon", {}).get("card_id", ""))
        if knowledge and opp_cid:
            return knowledge.is_ex(opp_cid)
    except Exception:
        pass
    return False
