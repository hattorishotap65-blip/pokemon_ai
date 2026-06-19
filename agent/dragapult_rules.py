"""
Dragapult ex deck-specific scoring bonuses.

Win condition:
  Dreepy -> Drakloak -> Dragapult ex  (Phantom Dive: spread 6 damage counters)
  Duskull -> Dusclops -> Dusknoir     (Ominous Diploma: spread 2 counters on evolve)
  Munkidori                           (ability: damage counter when opp plays energy)

score_bonus(action, state) returns (bonus: float, reason: str).
Return (0.0, "") when no Dragapult-specific logic applies.
Negative bonus discourages an action (e.g. discarding a key card).
"""

# -- Card IDs ------------------------------------------------------------------
_DREEPY      = "119"
_DRAKLOAK    = "120"
_DRAGAPULT   = "121"   # Dragapult ex — main attacker
_DUSKULL     = "131"
_DUSCLOPS    = "132"
_DUSKNOIR    = "133"   # Ominous Diploma: spread 2 counters on evolve
_MUNKIDORI   = "112"   # ability: damage counter when opp plays energy
_FEZANDIPITI = "140"   # Fezandipiti ex — bench support
_BUDEW       = "235"   # Budew — 1-prize starter / energy staller
_MEOWTH_EX   = "1071"  # Meowth ex — avoid as Active start

_RARE_CANDY      = "1079"
_BUDDYS_POFFIN   = "1086"
_ULTRA_BALL      = "1121"
_NIGHT_STRETCHER = "1097"
_BOSS_ORDERS     = "1182"
_LILLIES         = "1227"
_CRISPIN         = "1198"   # attach 2 Fire Energy from hand
_CRUSHING_HAMMER = "1120"   # flip to discard opp energy
_JAMMING_TOWER   = "1246"   # block ex abilities
_HANDHELD_FAN    = "1161"

# Opponent deck cards (Crustle 耐久デッキ)
_OPP_DWEBBLE = "344"
_OPP_CRUSTLE = "345"

# Energy card IDs
_DARK_ENERGY  = "7"
_FIRE_ENERGY  = "2"
_PSYCH_ENERGY = "5"

# Crustle base HP = 140; Hero's Cape adds 50 → max_hp > 140 means cape likely
_CRUSTLE_BASE_HP = 140

_DRAGAPULT_ENERGY_GOAL = 3

_AREA_ACTIVE = 4
_AREA_BENCH  = 5

# Opponent basic pre-evolution targets (good damage counter destinations)
_OPP_BASIC_PREEVOS = {
    "344",   # Dwebble → Crustle
    "722",   # Snover  → Abomasnow lines
    "677",   # Riolu   → Lucario lines
    "673",   # Makuhita → Hariyama lines
    "119",   # Dreepy  → Drakloak/Dragapult (mirror)
    "131",   # Duskull → Dusknoir line (mirror)
}

# Dragapult line card ID set for fast membership test
_DRAGAPULT_LINE = {_DREEPY, _DRAKLOAK, _DRAGAPULT}
# Dusk line
_DUSK_LINE      = {_DUSKULL, _DUSCLOPS, _DUSKNOIR}


# -- Our field helpers ---------------------------------------------------------

def _active_cid(state):
    return str(state.get("active_pokemon", {}).get("card_id", ""))

def _active_energy(state):
    return state.get("active_pokemon", {}).get("energy_count", 0)

def _active_hp_ratio(state):
    a = state.get("active_pokemon", {})
    mx = a.get("max_hp", 1) or 1
    return a.get("hp_remaining", mx) / mx

def _bench_cids(state):
    return [str(p.get("card_id", "")) for p in state.get("bench", [])]

def _dragapult_active(state):
    return _active_cid(state) == _DRAGAPULT

def _dragapult_on_field(state):
    return _DRAGAPULT in _bench_cids(state) or _dragapult_active(state)

def _dreepy_on_field(state):
    return _DREEPY in _bench_cids(state) or _active_cid(state) == _DREEPY

def _drakloak_on_field(state):
    return _DRAKLOAK in _bench_cids(state) or _active_cid(state) == _DRAKLOAK

def _duskull_on_field(state):
    return _DUSKULL in _bench_cids(state) or _active_cid(state) == _DUSKULL

def _dusclops_on_field(state):
    return _DUSCLOPS in _bench_cids(state) or _active_cid(state) == _DUSCLOPS

def _dusknoir_on_field(state):
    return _DUSKNOIR in _bench_cids(state) or _active_cid(state) == _DUSKNOIR

def _munkidori_on_bench(state):
    return _MUNKIDORI in _bench_cids(state)

def _dreepy_count(state):
    count = _bench_cids(state).count(_DREEPY)
    if _active_cid(state) == _DREEPY:
        count += 1
    return count

def _check_opp_ex(state, knowledge):
    try:
        opp_cid = str(state.get("opponent", {}).get("active_pokemon", {}).get("card_id", ""))
        if knowledge and opp_cid:
            return knowledge.is_ex(opp_cid)
    except Exception:
        pass
    return False


# -- Opponent field helpers ----------------------------------------------------

def _opp_active(state):
    return state.get("opponent", {}).get("active_pokemon", {})

def _opp_active_cid(state):
    return str(_opp_active(state).get("card_id", ""))

def _opp_active_energy(state):
    return _opp_active(state).get("energy_count", 0)

def _opp_active_max_hp(state):
    return _opp_active(state).get("max_hp", 0)

def _opp_bench(state):
    return state.get("opponent", {}).get("bench", [])

def _opp_bench_cids(state):
    return [str(p.get("card_id", "")) for p in _opp_bench(state)]

def _opp_crustle_active(state):
    return _opp_active_cid(state) == _OPP_CRUSTLE

def _opp_dwebble_on_bench(state):
    return _OPP_DWEBBLE in _opp_bench_cids(state)

def _opp_dwebble_active(state):
    return _opp_active_cid(state) == _OPP_DWEBBLE

def _opp_hero_cape_likely(state):
    """Heuristic: Crustle's observed max_hp exceeds base (140) → Hero's Cape attached."""
    if _opp_crustle_active(state):
        return _opp_active_max_hp(state) > _CRUSTLE_BASE_HP
    return False

def _opp_is_crustle_deck(state):
    opp_cids = set(_opp_bench_cids(state)) | {_opp_active_cid(state)}
    return bool(opp_cids & {_OPP_CRUSTLE, _OPP_DWEBBLE})

def _opp_bench_has_near_ko(state, threshold=20):
    for p in _opp_bench(state):
        if p.get("hp_remaining", 9999) <= threshold:
            return True
    return False

def _opp_bench_has_weak_pokemon(state):
    for p in _opp_bench(state):
        hp     = p.get("hp_remaining", 9999)
        max_hp = p.get("max_hp", 1) or 1
        if hp <= 60 or hp / max_hp <= 0.3:
            return True
    return False


# -- Helpers for TO_BENCH / setup context --------------------------------------

def _count_own(state: dict, *card_ids: str) -> int:
    """Count how many of the given card IDs appear on our field (active + bench)."""
    count = 0
    active_cid = _active_cid(state)
    for cid in card_ids:
        if active_cid == cid:
            count += 1
        count += sum(1 for p in state.get("bench", []) if str(p.get("card_id", "")) == cid)
    return count


def _get_energy_ids(pokemon_dict: dict) -> list:
    """
    Return list of energy type ID strings for a normalized pokemon dict.

    Prefers the pre-resolved 'energy_types' field (list[int]) written by
    main._normalize_pokemon().  Falls back to parsing 'energies' directly
    when 'energy_types' is absent (e.g. in unit tests or rollout states).
    Always returns list[str] so callers can use 'in' comparisons against
    string constants like _FIRE_ENERGY = "2".
    """
    # Fast path: already resolved by _normalize_pokemon
    energy_types = pokemon_dict.get("energy_types")
    if energy_types is not None:
        return [str(e) for e in energy_types]

    # Fallback: parse raw energies (handles IntEnum / dict / object forms)
    _NAME_MAP = {
        "FIRE": "2", "PSYCHIC": "5", "DARKNESS": "7", "DARK": "7",
        "WATER": "3", "LIGHTNING": "4", "FIGHTING": "6", "GRASS": "1",
        "METAL": "8", "FAIRY": "9", "DRAGON": "10", "COLORLESS": "11",
    }
    result = []
    for e in (pokemon_dict.get("energies") or []):
        eid = None
        if isinstance(e, int):
            eid = e
        elif isinstance(e, dict):
            eid = e.get("id") or e.get("card_id") or e.get("type")
        else:
            try:
                eid = int(e)
            except Exception:
                eid = getattr(e, "id", None)
                if eid is None:
                    val = getattr(e, "value", None)
                    if val is not None:
                        try:
                            eid = int(val)
                        except (TypeError, ValueError):
                            pass
                if eid is None:
                    name = str(getattr(e, "name", "")).upper()
                    eid = _NAME_MAP.get(name)
        if eid is not None and eid != "":
            result.append(str(eid))
    return result


def _dragapult_energy_ready(state: dict) -> bool:
    """True when any Dragapult ex has Fire+Psychic energies and meets count goal."""
    def _check(pokemon_dict):
        eids = _get_energy_ids(pokemon_dict)
        return (
            _FIRE_ENERGY  in eids
            and _PSYCH_ENERGY in eids
            and len(eids) >= _DRAGAPULT_ENERGY_GOAL
        )
    if _active_cid(state) == _DRAGAPULT and _check(state.get("active_pokemon", {})):
        return True
    for p in state.get("bench", []):
        if str(p.get("card_id", "")) == _DRAGAPULT and _check(p):
            return True
    return False


def _munkidori_has_dark_energy(state: dict) -> bool:
    """True when Munkidori on field has at least one Dark energy attached."""
    def _check(pokemon_dict):
        return _DARK_ENERGY in _get_energy_ids(pokemon_dict)
    if _active_cid(state) == _MUNKIDORI and _check(state.get("active_pokemon", {})):
        return True
    for p in state.get("bench", []):
        if str(p.get("card_id", "")) == _MUNKIDORI and _check(p):
            return True
    return False


def _score_tool_attachment_bonus(
    attach_cid: str, target_cid: str, state: dict
) -> tuple[float, str]:
    """
    Deck-specific bonus/penalty for attaching a Tool card.
    policy.py already handles the primary tool scoring (_score_attach_tool);
    this function provides incremental context from the Dragapult deck rules.
    Returns (0.0, reason_tag) for most cases to avoid double-counting.
    """
    _DUSK_SET = {_DUSKULL, _DUSCLOPS, _DUSKNOIR}
    _SUP_EX   = {_FEZANDIPITI, _MEOWTH_EX}

    if attach_cid == _HANDHELD_FAN:
        if target_cid == _DRAGAPULT:
            return 0.0, "tool_fan_dragapult_ex"
        if target_cid in _DRAGAPULT_LINE:
            return 0.0, "tool_fan_dragapult_line"
        if target_cid in _DUSK_SET or target_cid in _SUP_EX or target_cid == _BUDEW:
            return -3.0, "tool_fan_avoid_non_attacker"
        return 0.0, "tool_fan_generic"

    # Hero's Cape (1159) — adds +50 HP; already scored in policy
    if target_cid in _DUSK_SET or target_cid in _SUP_EX or target_cid == _BUDEW:
        return -3.0, "tool_cape_avoid_non_attacker"
    if target_cid in _DRAGAPULT_LINE:
        return 0.0, "tool_cape_dragapult_line"
    return 0.0, "tool_generic"


def score_energy_attachment(
    energy_cid: str, target_cid: str, state: dict
) -> tuple[float, str]:
    """
    Score energy-type × target-Pokemon compatibility for ATTACH actions.

    Returns (bonus, pipe-separated reason).
    Strongly positive for correct type→target pairs,
    strongly negative for mismatches.
    Returns (0.0, "") when the combination is not Dragapult-specific.
    """
    score  = 0.0
    parts: list[str] = []

    _FIRE_SET = (_FIRE_ENERGY, _PSYCH_ENERGY)
    _SUP_EX   = {_FEZANDIPITI, _MEOWTH_EX}

    # --- Beneficial pairings ---

    # Fire / Psychic → Dragapult line (Dreepy / Drakloak / Dragapult ex)
    if energy_cid in _FIRE_SET and target_cid in _DRAGAPULT_LINE:
        score += 20.0
        parts.append("attach_fire_psychic_to_dragapult_line")
        ready = _dragapult_energy_ready(state)
        if not ready:
            score += 10.0
            parts.append("complete_dragapult_energy_req")
        else:
            parts.append("dragapult_already_ready")

    # Dark → Munkidori
    if energy_cid == _DARK_ENERGY and target_cid == _MUNKIDORI:
        score += 20.0
        parts.append("attach_dark_to_munkidori")
        has_dark = _munkidori_has_dark_energy(state)
        if not has_dark:
            score += 8.0
            parts.append("enable_munkidori_ability")
        else:
            parts.append("munkidori_already_has_dark")

    # --- Harmful pairings ---

    # Fire / Psychic → Munkidori (wrong energy type)
    if target_cid == _MUNKIDORI and energy_cid in _FIRE_SET:
        score -= 15.0
        parts.append("avoid_non_dark_to_munkidori")

    # Any energy → Dusk line (Duskull / Dusclops / Dusknoir never need energy)
    if target_cid in _DUSK_LINE:
        score -= 20.0
        parts.append("avoid_attach_dusk_line")

    # Any energy → Budew
    if target_cid == _BUDEW:
        score -= 15.0
        parts.append("avoid_attach_budew")

    # Any energy → Support EX (Fezandipiti ex / Meowth ex)
    if target_cid in _SUP_EX:
        score -= 15.0
        parts.append("avoid_attach_support_ex")

    # Dark → Dragapult line (Fire+Psychic required; Dark wastes an energy slot)
    if energy_cid == _DARK_ENERGY and target_cid in _DRAGAPULT_LINE:
        score -= 12.0
        parts.append("avoid_dark_to_dragapult_line")

    return score, "|".join(parts)


def _score_poffin_bench(cid: str, state: dict) -> tuple[float, str]:
    """
    Prioritise Dreepy when fetching with Buddy-Buddy Poffin (or any TO_BENCH
    context that offers both Dreepy and Duskull).
    """
    dreepy_count  = _count_own(state, _DREEPY)
    duskull_count = _count_own(state, _DUSKULL)

    if cid == _DREEPY:
        if dreepy_count == 0:
            return 100.0, "poffin_first_dreepy"
        if dreepy_count == 1:
            return 90.0,  "poffin_second_dreepy"
        return 60.0, "poffin_extra_dreepy"

    if cid == _DUSKULL:
        if dreepy_count < 2:
            return 40.0, "poffin_delay_duskull_until_dreepy"
        if duskull_count == 0:
            return 75.0, "poffin_first_duskull"
        return 45.0, "poffin_extra_duskull"

    return 0.0, ""


# -- Main entry point ----------------------------------------------------------

def score_bonus(action: dict, state: dict, knowledge=None) -> tuple[float, str]:
    """
    Return (bonus, reason) for Dragapult ex deck-specific actions.
    bonus is ADDED to the base policy score; negative = discourage.
    """
    opt_type = action.get("type")
    cid = str(action.get("resolved_card_id") or action.get("cardId") or "")
    ctx = action.get("select_context")

    # -- 1. Evolve Drakloak -> Dragapult ex -----------------------------------
    if opt_type == 9 and cid == _DRAGAPULT:
        return 10.0, "dragapult:evolve_dragapult"

    # -- 2. Evolve Dusclops -> Dusknoir (spread on evolve) --------------------
    # +6 keeps it below Drakloak (+7) so Dragapult line stays top priority
    if opt_type == 9 and cid == _DUSKNOIR:
        return 6.0, "dragapult:evolve_dusknoir"

    # -- 3. Evolve Dreepy -> Drakloak ------------------------------------------
    if opt_type == 9 and cid == _DRAKLOAK:
        return 7.0, "dragapult:evolve_drakloak"

    # -- 4. Evolve Duskull -> Dusclops -----------------------------------------
    if opt_type == 9 and cid == _DUSCLOPS:
        return 5.0, "dragapult:evolve_dusclops"

    # -- 5. Play Dreepy — count-aware deployment --------------------------------
    if opt_type == 7 and cid == _DREEPY:
        bench = state.get("bench", [])
        if len(bench) < 5:
            cnt   = _dreepy_count(state)
            bonus = 7.0 if cnt == 0 else (6.0 if cnt == 1 else 4.0)
            return bonus, "dragapult:play_dreepy"

    # -- 6. Play Duskull — only after Dreepy ≥2 or Dragapult on field ---------
    if opt_type == 7 and cid == _DUSKULL:
        bench = state.get("bench", [])
        if len(bench) < 5 and not _dusknoir_on_field(state):
            if _dreepy_count(state) >= 2 or _dragapult_on_field(state):
                return 4.0, "dragapult:play_duskull"
            return 2.0, "dragapult:play_duskull_low_priority"

    # -- 7. Play Munkidori (spread damage ability) ----------------------------
    if opt_type == 7 and cid == _MUNKIDORI:
        if not _munkidori_on_bench(state):
            return 3.5, "dragapult:play_munkidori"

    # -- 8. Attack with Dragapult ex (Phantom Dive) ---------------------------
    # Extra +2 when Dwebble is on opponent bench (deny Crustle evolution)
    if opt_type == 13 and _dragapult_active(state):
        energy = _active_energy(state)
        if energy >= _DRAGAPULT_ENERGY_GOAL:
            opp_is_ex     = _check_opp_ex(state, knowledge)
            ex_bonus      = 2.0 if opp_is_ex else 0.0
            dwebble_bonus = 2.0 if _opp_dwebble_on_bench(state) else 0.0
            return 5.0 + ex_bonus + dwebble_bonus, "dragapult:phantom_dive"

    # -- 9. ATTACH (opt_type=8) — unified energy-type × target scoring ---------
    # inPlayArea/inPlayIndex = target Pokemon position (NOT action.get("area")
    # which is the HAND area of the energy card being attached).
    if opt_type == 8:
        _TOOL_CIDS   = {"1159", "1161"}  # Hero's Cape, Handheld Fan
        _ENERGY_CIDS = {_FIRE_ENERGY, _PSYCH_ENERGY, _DARK_ENERGY}
        target_area = action.get("inPlayArea")
        target_idx  = action.get("inPlayIndex")
        e_cid       = str(action.get("resolved_card_id") or "")

        is_tool = e_cid in _TOOL_CIDS or (
            knowledge is not None
            and (knowledge.get_role(e_cid) == "tool"
                 or knowledge.has_tag(e_cid, "tool"))
        )
        if is_tool:
            attach_kind = "tool"
        elif e_cid in _ENERGY_CIDS:
            attach_kind = "energy"
        else:
            attach_kind = "unknown"

        if target_area == _AREA_ACTIVE:
            t_cid = _active_cid(state)
        elif target_area == _AREA_BENCH and target_idx is not None:
            bench = state.get("bench", [])
            t_cid = str(bench[target_idx].get("card_id", "")) if target_idx < len(bench) else ""
        else:
            t_cid = ""

        if attach_kind == "energy":
            if e_cid and t_cid:
                esc, ereason = score_energy_attachment(e_cid, t_cid, state)
                if ereason:
                    return esc, f"dragapult:attach_energy|{ereason}"
            # Energy with no specific rule → fall through to return 0.0, ""

        elif attach_kind == "tool":
            tsc, treason = _score_tool_attachment_bonus(e_cid, t_cid, state)
            return tsc, f"dragapult:attach_tool|{treason}"

        else:
            if e_cid:
                return 0.0, "dragapult:attach_unknown"

    # -- 11. Rare Candy -------------------------------------------------------
    if opt_type == 7 and cid == _RARE_CANDY:
        if _dreepy_on_field(state) and not _drakloak_on_field(state):
            return 5.0, "dragapult:rare_candy_dreepy_to_dragapult"
        if _duskull_on_field(state) and not _dusclops_on_field(state):
            # Higher bonus only when Dusknoir's spread would enable a KO
            ko_enabled = _opp_bench_has_near_ko(state, threshold=20)
            return (4.0 if ko_enabled else 2.0), "dragapult:rare_candy_duskull_to_dusknoir"

    # -- 12. Crispin — Fire energy acceleration --------------------------------
    if opt_type == 7 and cid == _CRISPIN:
        if _dragapult_active(state) and _active_energy(state) < _DRAGAPULT_ENERGY_GOAL:
            return 4.0, "dragapult:crispin_for_dragapult"
        return 2.5, "dragapult:crispin"

    # -- 13. Crushing Hammer — Crustle energy-count-aware disruption ----------
    if opt_type == 7 and cid == _CRUSHING_HAMMER:
        if _opp_crustle_active(state):
            opp_e = _opp_active_energy(state)
            bonus = 5.0 if opp_e >= 3 else (4.0 if opp_e >= 1 else 3.0)
            return bonus, "dragapult:crushing_hammer_crustle"
        if _opp_dwebble_active(state) or _opp_dwebble_on_bench(state):
            return 3.5, "dragapult:crushing_hammer_dwebble"
        return 2.0, "dragapult:crushing_hammer"

    # -- 14. Jamming Tower — Hero's Cape / Crustle-aware ----------------------
    if opt_type == 7 and cid == _JAMMING_TOWER:
        if _opp_hero_cape_likely(state):
            return 6.0, "dragapult:jamming_tower_hero_cape"
        if _opp_is_crustle_deck(state):
            return 3.5, "dragapult:jamming_tower_crustle"
        return 2.5, "dragapult:jamming_tower"

    # -- 15. Buddy-Buddy Poffin — PLAY decision --------------------------------
    # Score how valuable it is to PLAY the Poffin (not which Pokemon to fetch).
    if opt_type == 7 and cid == _BUDDYS_POFFIN:
        cnt = _dreepy_count(state)
        if cnt == 0:
            return 6.0, "dragapult:poffin_urgent_dreepy"
        if cnt == 1:
            return 5.0, "dragapult:poffin_second_dreepy"
        if not _duskull_on_field(state) and not _dusknoir_on_field(state):
            return 3.5, "dragapult:poffin_duskull"
        return 2.0, "dragapult:poffin_low_priority"

    # -- 15b. TO_BENCH context — fetch target (Poffin / any bench-search) -----
    # ctx == 5 is SelectContext.TO_BENCH; applies when fetching a Pokemon to bench.
    if ctx == 5 and cid in (_DREEPY, _DUSKULL):
        score, reason = _score_poffin_bench(cid, state)
        if score > 0.0:
            return score, f"dragapult:{reason}"

    # -- 16. Boss's Orders — Dwebble priority / KO race / weak target --------
    if opt_type == 7 and cid == _BOSS_ORDERS:
        if _opp_dwebble_on_bench(state):
            return 5.0, "dragapult:boss_dwebble"
        opp_prizes = state.get("opponent", {}).get("prizes_remaining", 6)
        if (opp_prizes <= 2
                and _dragapult_active(state)
                and _active_energy(state) >= _DRAGAPULT_ENERGY_GOAL):
            return 4.0, "dragapult:boss_for_ko"
        if _opp_bench_has_weak_pokemon(state):
            return 3.5, "dragapult:boss_weak_target"

    # -- 19. Night Stretcher — recover Dragapult line or energy ---------------
    if opt_type == 7 and cid == _NIGHT_STRETCHER:
        return 1.5, "dragapult:night_stretcher"

    # -- 20. TO_HAND context — prioritize key pieces --------------------------
    if ctx == 7:   # SelectContext.TO_HAND
        if cid == _DRAGAPULT:
            return 4.0, "dragapult:search_dragapult"
        if cid == _DRAKLOAK:
            return 3.5, "dragapult:search_drakloak"
        if cid == _DUSKNOIR:
            return 3.5, "dragapult:search_dusknoir"
        if cid == _DREEPY and not _dreepy_on_field(state):
            return 3.0, "dragapult:search_dreepy"
        if cid == _DUSKULL and not _duskull_on_field(state):
            return 2.5, "dragapult:search_duskull"
        if cid == _RARE_CANDY:
            return 2.0, "dragapult:search_rare_candy"

    # -- 21. ATTACH_FROM (ctx=21): target Dragapult ex ------------------------
    if opt_type == 3 and ctx == 21:
        area    = action.get("area")
        idx_val = action.get("index")
        if area == _AREA_ACTIVE and _dragapult_active(state):
            return 3.0, "dragapult:attach_to_dragapult_active"
        if area == _AREA_BENCH and idx_val is not None:
            bench = state.get("bench", [])
            if idx_val < len(bench):
                if str(bench[idx_val].get("card_id", "")) == _DRAGAPULT:
                    return 2.0, "dragapult:attach_to_dragapult_bench"

    # -- 22. EVOLVES_TO context (ctx=19): prefer Dragapult ex -----------------
    if ctx == 19:
        if cid == _DRAGAPULT:
            return 4.0, "dragapult:evolves_to_dragapult"
        if cid == _DUSKNOIR:
            return 3.0, "dragapult:evolves_to_dusknoir"
        if cid == _DRAKLOAK:
            return 2.0, "dragapult:evolves_to_drakloak"

    # -- 23. Lillie's Determination — hand quality gate -----------------------
    # Only worth playing when the hand is genuinely bad.  Penalise if it would
    # shuffle away key combo pieces that are hard to re-draw.
    if opt_type == 7 and cid == _LILLIES:
        hand = [str(c) for c in (state.get("hand") or [])]
        hand_set = set(hand)

        # Hard stop: don't shuffle away win-condition combos
        if _RARE_CANDY in hand_set and _DRAGAPULT in hand_set:
            return -10.0, "dragapult:lillies_keep_rare_candy_dragapult"
        if _DRAKLOAK in hand_set and _DRAGAPULT in hand_set:
            return -8.0, "dragapult:lillies_keep_evolution_chain"
        if _BOSS_ORDERS in hand_set and _opp_dwebble_on_bench(state):
            return -8.0, "dragapult:lillies_keep_boss_dwebble"
        if _BOSS_ORDERS in hand_set and _opp_bench_has_weak_pokemon(state):
            return -5.0, "dragapult:lillies_keep_boss_weak_target"
        if _CRISPIN in hand_set and _dragapult_active(state) and _active_energy(state) < _DRAGAPULT_ENERGY_GOAL:
            return -6.0, "dragapult:lillies_keep_crispin_for_energy"

        # Positive: genuinely bad hand (no Dreepy, no search, no evolution)
        has_dreepy_on_field = _dreepy_on_field(state) or _drakloak_on_field(state) or _dragapult_on_field(state)
        has_search = any(c in hand_set for c in (_BUDDYS_POFFIN, _ULTRA_BALL, _RARE_CANDY))
        has_evolution = any(c in hand_set for c in (_DRAKLOAK, _DRAGAPULT, _DUSCLOPS, _DUSKNOIR))
        has_energy = any(c in hand_set for c in (_FIRE_ENERGY, _PSYCH_ENERGY, _DARK_ENERGY))
        hand_quality_ok = has_dreepy_on_field or has_search or has_evolution or has_energy
        if not hand_quality_ok:
            return 6.0, "dragapult:lillies_fix_bad_hand"

        # Moderately bad: no Dreepy on field and no search cards
        if not has_dreepy_on_field and not has_search:
            return 4.0, "dragapult:lillies_need_setup"

    # -- 25. SETUP_ACTIVE (ctx=1) — initial Active Pokemon priority -----------
    if ctx == 1:   # SelectContext.SETUP_ACTIVE
        if cid == _DREEPY:
            return 30.0, "dragapult:start_dreepy"
        if cid == _BUDEW:
            return 20.0, "dragapult:start_budew"
        if cid == _MUNKIDORI:
            return 15.0, "dragapult:start_munkidori"
        if cid == _DUSKULL:
            return 10.0, "dragapult:start_duskull"
        if cid in (_FEZANDIPITI, _MEOWTH_EX):
            return -30.0, "dragapult:avoid_two_prize_start"

    # -- 26. DAMAGE_COUNTER targets — pre-evolution and low-HP priority -------
    if ctx in (13, 14, 15):   # DAMAGE_COUNTER / DAMAGE_COUNTER_ANY / DAMAGE
        area      = action.get("area")
        idx_val   = action.get("index")
        remain_dc = int(action.get("remain_damage_counter") or 0)

        my_idx    = state.get("your_index", 0)
        p_idx     = action.get("playerIndex")
        is_own    = (p_idx is not None and int(p_idx) == my_idx)
        if is_own:
            return 0.0, ""   # let base policy handle own-Pokemon placement

        opp = state.get("opponent", {})
        if area == _AREA_ACTIVE:
            target = opp.get("active_pokemon", {})
        elif area == _AREA_BENCH and idx_val is not None:
            bench = opp.get("bench", [])
            target = bench[idx_val] if idx_val < len(bench) else {}
        else:
            target = {}

        target_cid = str(target.get("card_id", ""))
        hp         = int(target.get("hp_remaining") or 9999)
        is_ex      = knowledge.has_tag(target_cid, "ex") if knowledge and target_cid else False

        bonus = 0.0
        reason = ""

        # Pre-evolution targets — easy KOs later
        if target_cid in _OPP_BASIC_PREEVOS:
            bonus  += 12.0
            reason  = "dragapult:damage_target_basic_pre_evolution"

        # Low HP — near-KO window
        if hp <= 60 and hp > 0:
            bonus  += 15.0
            reason  = "dragapult:damage_target_low_hp" if not reason else reason

        # Large ex with no KO potential — avoid splitting counters
        if is_ex and remain_dc > 0 and hp > remain_dc * 10:
            bonus  -= 5.0
            if not reason:
                reason = "dragapult:avoid_large_ex_no_ko"

        if bonus != 0.0:
            return bonus, reason

    return 0.0, ""
