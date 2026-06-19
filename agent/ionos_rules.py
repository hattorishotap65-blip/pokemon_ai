"""
Iono's Kilowattrel deck — deck-specific scoring bonuses.

Main plan:
  Iono's Voltorb (265)       — early attacker; damage = 20 + 20*(Lightning on all Iono's Pokemon)
  Iono's Tadbulb (268)       -> Iono's Bellibolt ex (269) — engine (ability: attach Lightning) + main attacker
  Iono's Wattrel  (270)      -> Iono's Kilowattrel (271)  — sub attacker

Key mechanic: Bellibolt ex ability lets you attach Lightning energies to Iono's Pokemon.
Every Lightning on any Iono's Pokemon raises Voltorb's damage by 20.
Single energy type (Lightning only) — no color mismatch.

score_bonus(action, state, knowledge) returns (bonus: float, reason: str).
Negative bonus discourages an action.
"""

# -- Card IDs ------------------------------------------------------------------
_VOLTORB      = "265"
_TADBULB      = "268"
_BELLIBOLT_EX = "269"
_WATTREL      = "270"
_KILOWATTREL  = "271"

_BUDDYS_POFFIN    = "1086"
_ULTRA_BALL       = "1121"
_NIGHT_STRETCHER  = "1097"
_LILLIES          = "1227"
_CANARI           = "1233"
_LEVINCIA         = "1254"
_POKE_PAD         = "1152"
_ENERGY_RETRIEVAL = "1118"
_MAX_ROD          = "1110"

_LIGHTNING_ENERGY = "4"

# All Iono's Pokemon — total Lightning on these powers Voltorb's damage
_IONO_LINE = {_VOLTORB, _TADBULB, _BELLIBOLT_EX, _WATTREL, _KILOWATTREL}

# Aliases (shorter names for setup logic)
_POFFIN = _BUDDYS_POFFIN
_LILLIE = _LILLIES

# Sets for membership tests (string IDs match resolved_card_id / _cid_from_hand output)
IONO_POKEMON_IDS  = frozenset({_VOLTORB, _TADBULB, _BELLIBOLT_EX, _WATTREL, _KILOWATTREL})
IONO_BASIC_IDS    = frozenset({_VOLTORB, _TADBULB, _WATTREL})
SETUP_SUPPORT_IDS = frozenset({_BUDDYS_POFFIN, _ULTRA_BALL, _LILLIES, _CANARI, _LEVINCIA})

_AREA_ACTIVE = 4
_AREA_BENCH  = 5

# Option type classification — single source of truth
try:
    from agent.turn_rule_engine import (
        is_attack_option  as _is_attack,
        is_ability_option as _is_ability,
        is_retreat_option as _is_retreat,
        is_end_option     as _is_end,
    )
except ImportError:
    def _is_attack(opt):  return opt.get("type") == 13 and opt.get("attackId") is not None  # type: ignore[misc]
    def _is_ability(opt): return opt.get("type") == 10  # type: ignore[misc]
    def _is_retreat(opt): return opt.get("type") == 12  # type: ignore[misc]
    def _is_end(opt):     return opt.get("type") == 14  # type: ignore[misc]

# Fallback energy requirements (game's legal moves take priority)
_VOLTORB_ATTACK_ENERGY_REQ     = 2
_BELLIBOLT_ATTACK_ENERGY_REQ   = 4   # official text: LLLC (4 energy)
_KILOWATTREL_ATTACK_ENERGY_REQ = 3

# Bellibolt ex damage (official text: fixed 230 for Thunderous Bolt)
BELLIBOLT_ATTACK_DAMAGE = 230


# -- Field helpers -------------------------------------------------------------

def _active_cid(state: dict) -> str:
    return str(state.get("active_pokemon", {}).get("card_id", ""))

def _active_energy_count(state: dict) -> int:
    return state.get("active_pokemon", {}).get("energy_count", 0)

def _bench_cids(state: dict) -> list:
    return [str(p.get("card_id", "")) for p in state.get("bench", [])]

def _count_own(state: dict, *card_ids: str) -> int:
    """Count instances of given card IDs on our field (active + bench)."""
    count  = 0
    active = _active_cid(state)
    for cid in card_ids:
        if active == cid:
            count += 1
        count += sum(1 for p in state.get("bench", []) if str(p.get("card_id", "")) == cid)
    return count

def _voltorb_on_field(state):
    return _VOLTORB in _bench_cids(state) or _active_cid(state) == _VOLTORB

def _tadbulb_on_field(state):
    return _TADBULB in _bench_cids(state) or _active_cid(state) == _TADBULB

def _wattrel_on_field(state):
    return _WATTREL in _bench_cids(state) or _active_cid(state) == _WATTREL

def _bellibolt_on_field(state):
    return _BELLIBOLT_EX in _bench_cids(state) or _active_cid(state) == _BELLIBOLT_EX

def _kilowattrel_on_field(state):
    return _KILOWATTREL in _bench_cids(state) or _active_cid(state) == _KILOWATTREL


def _get_energy_ids(pokemon_dict: dict) -> list:
    """Return list[str] of energy type IDs for a normalized pokemon dict."""
    energy_types = pokemon_dict.get("energy_types")
    if energy_types is not None:
        return [str(e) for e in energy_types]
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


def _count_lightning_on_iono_pokemon(state: dict) -> int:
    """Count total Lightning energy on all our Iono's Pokemon (drives Voltorb damage)."""
    total    = 0
    all_mons = [state.get("active_pokemon") or {}] + list(state.get("bench") or [])
    for p in all_mons:
        if not p:
            continue
        if str(p.get("card_id", "")) not in _IONO_LINE:
            continue
        for eid in _get_energy_ids(p):
            if eid == _LIGHTNING_ENERGY:
                total += 1
    return total


def _estimate_voltorb_damage(state: dict) -> int:
    """Estimate Voltorb's current damage (20 + 20 * total Lightning on Iono's mons)."""
    return 20 + 20 * _count_lightning_on_iono_pokemon(state)


def estimate_bellibolt_damage(state: dict) -> tuple:
    """Bellibolt ex damage: official text Thunderous Bolt → fixed 230."""
    return BELLIBOLT_ATTACK_DAMAGE, "bellibolt_official_lllc_230"


def _get_target_energy_count(target_cid: str, state: dict) -> int:
    """Return current energy count for a specific Pokemon on our field."""
    if _active_cid(state) == target_cid:
        return _active_energy_count(state)
    for p in state.get("bench", []):
        if str(p.get("card_id", "")) == target_cid:
            return p.get("energy_count", 0)
    return 0


# -- Setup / hand helpers ------------------------------------------------------

def _count_in_hand(state: dict, cid: str) -> int:
    """Count occurrences of card ID string in hand (internal state dict)."""
    return (state.get("hand") or []).count(cid)

def _bench_size(state: dict) -> int:
    return len(state.get("bench") or [])

def _energy_in_hand_count(state: dict) -> int:
    return _count_in_hand(state, _LIGHTNING_ENERGY)

def _iono_basic_in_play_count(state: dict) -> int:
    return _count_own(state, _VOLTORB) + _count_own(state, _TADBULB) + _count_own(state, _WATTREL)

def _setup_missing_flags(state: dict) -> dict:
    return {
        "bench_count":            _bench_size(state),
        "basic_count":            _iono_basic_in_play_count(state),
        "has_voltorb":            _count_own(state, _VOLTORB)    > 0,
        "has_tadbulb":            _count_own(state, _TADBULB)    > 0,
        "has_wattrel":            _count_own(state, _WATTREL)    > 0,
        "has_bellibolt":          _count_own(state, _BELLIBOLT_EX)  > 0,
        "has_kilowattrel":        _count_own(state, _KILOWATTREL)   > 0,
        "energy_in_hand":         _energy_in_hand_count(state),
        "has_poffin_in_hand":     _count_in_hand(state, _BUDDYS_POFFIN) > 0,
        "has_ultra_ball_in_hand": _count_in_hand(state, _ULTRA_BALL)    > 0,
        "has_lillie_in_hand":     _count_in_hand(state, _LILLIES)       > 0,
        "has_canari_in_hand":     _count_in_hand(state, _CANARI)        > 0,
        "has_levincia_in_hand":   _count_in_hand(state, _LEVINCIA)      > 0,
    }

def _is_setup_poor(state: dict) -> bool:
    f = _setup_missing_flags(state)
    if f["bench_count"] == 0:                               return True
    if f["basic_count"] <= 1:                               return True
    if not f["has_voltorb"]:                                return True
    if not f["has_tadbulb"]:                                return True
    if f["energy_in_hand"] >= 4 and f["basic_count"] <= 2: return True
    return False


# -- Tool (none in this deck) --------------------------------------------------

def _score_tool_attachment_bonus(
    attach_cid: str, target_cid: str, state: dict
) -> tuple:
    """No tool cards in Iono's deck."""
    return 0.0, "ionos:no_tool_in_deck"


# -- Energy attachment helpers -------------------------------------------------

_ATTACK_ENERGY_REQ_MAP = {
    _VOLTORB:      _VOLTORB_ATTACK_ENERGY_REQ,       # 2
    _KILOWATTREL:  _KILOWATTREL_ATTACK_ENERGY_REQ,    # 3
    _BELLIBOLT_EX: _BELLIBOLT_ATTACK_ENERGY_REQ,      # 4
}


def _energy_needed_to_attack(target_cid: str, target_energy: int):
    """Return energy still needed to attack, or None if not an attacker."""
    req = _ATTACK_ENERGY_REQ_MAP.get(target_cid)
    if req is None:
        return None
    return max(0, req - target_energy)


def _would_enable_attack(target_cid: str, target_energy: int) -> bool:
    """True if attaching 1 more energy would enable attack."""
    needed = _energy_needed_to_attack(target_cid, target_energy)
    return needed == 1


def _score_attach_core(
    target_cid: str, state: dict, target_energy: int, prefix: str,
) -> tuple:
    """
    Shared attach-target scoring for both normal and Bellibolt-engine mode.

    Evaluation axes (highest to lowest):
      1. Enables attack this attach        (+300 + card bonus)
      2. KO line reached by Voltorb damage (+400)
      3. Card-specific value
      4. Voltorb damage increase           (+35)
      5. Over-attach penalty
    """
    score = 0.0
    parts: list = []
    needed = _energy_needed_to_attack(target_cid, target_energy)

    # --- Axis 1: attack enablement ---
    if _would_enable_attack(target_cid, target_energy):
        score += 300.0
        parts.append(f"{prefix}:attach_enables_attack")
        if target_cid == _VOLTORB:
            score += 100.0; parts.append(f"{prefix}:enables_voltorb_attack")
        elif target_cid == _BELLIBOLT_EX:
            score += 90.0;  parts.append(f"{prefix}:enables_bellibolt_attack")
        elif target_cid == _KILOWATTREL:
            score += 80.0;  parts.append(f"{prefix}:enables_kilowattrel_attack")
    elif needed == 0:
        score -= 60.0
        parts.append(f"{prefix}:target_already_ready")
    elif needed is not None and needed >= 2:
        score += 40.0
        parts.append(f"{prefix}:progress_future_attacker")

    # --- Axis 2: card-specific value ---
    if target_cid == _VOLTORB:
        if target_energy == 0:
            score += 70.0;  parts.append(f"{prefix}:voltorb_first_energy")
        elif target_energy == 1:
            score += 140.0; parts.append(f"{prefix}:voltorb_enable_attack")
        elif target_energy >= 2:
            score -= 80.0;  parts.append(f"{prefix}:voltorb_over_attach")
    elif target_cid == _BELLIBOLT_EX:
        if target_energy == 0:
            score += 50.0;  parts.append(f"{prefix}:bellibolt_first_energy")
        elif needed == 1:
            score += 100.0; parts.append(f"{prefix}:bellibolt_close_to_attack")
        elif needed == 0:
            score -= 50.0;  parts.append(f"{prefix}:bellibolt_over_attach")
        else:
            score += 30.0;  parts.append(f"{prefix}:bellibolt_prep")
    elif target_cid == _KILOWATTREL:
        if target_energy == 0:
            score += 45.0;  parts.append(f"{prefix}:kilowattrel_first_energy")
        elif needed == 1:
            score += 100.0; parts.append(f"{prefix}:kilowattrel_close_to_attack")
        elif needed == 0:
            score -= 50.0;  parts.append(f"{prefix}:kilowattrel_over_attach")
        else:
            score += 30.0;  parts.append(f"{prefix}:kilowattrel_prep")
    elif target_cid == _TADBULB:
        if target_energy == 0:
            score += 45.0;  parts.append(f"{prefix}:tadbulb_first_energy")
        else:
            score -= 20.0;  parts.append(f"{prefix}:tadbulb_too_much")
    elif target_cid == _WATTREL:
        if target_energy == 0:
            score += 45.0;  parts.append(f"{prefix}:wattrel_first_energy")
        else:
            score -= 20.0;  parts.append(f"{prefix}:wattrel_too_much")

    # --- Axis 3: Voltorb damage increase ---
    if target_cid in _IONO_LINE:
        score += 35.0
        parts.append(f"{prefix}:increases_voltorb_damage")

    # --- Axis 4: KO line check ---
    opp_hp = state.get("opponent", {}).get("active_pokemon", {}).get("hp_remaining", 9999)
    if opp_hp < 9999:
        before_dmg = _estimate_voltorb_damage(state)
        after_dmg  = before_dmg + (20 if target_cid in _IONO_LINE else 0)
        if after_dmg >= opp_hp > 0 and before_dmg < opp_hp:
            score += 400.0
            parts.append(f"{prefix}:reaches_voltorb_ko_line")

    return score, "|".join(parts)


# -- Energy attachment scoring -------------------------------------------------

def score_energy_attachment(
    energy_cid: str, target_cid: str, state: dict, target_energy: int = None
) -> tuple:
    """
    Score Lightning energy x target-Pokemon (normal mode, no Bellibolt engine).
    Attack-enablement is the primary axis.
    """
    if energy_cid != _LIGHTNING_ENERGY:
        return -20.0, "ionos:non_lightning_energy"
    if target_cid not in _IONO_LINE:
        return -20.0, "ionos:avoid_non_iono_pokemon"
    if target_energy is None:
        target_energy = _get_target_energy_count(target_cid, state)
    return _score_attach_core(target_cid, state, target_energy, "normal")


# -- Bellibolt ex energy acceleration scoring ---------------------------------

def score_bellibolt_energy_attach(
    energy_cid: str, target_cid: str, state: dict, target_energy: int = None
) -> tuple:
    """
    Score energy attachment when Bellibolt ex is on field (engine mode).
    Same attack-enablement logic as normal, plus a small ability bonus.
    """
    if energy_cid != _LIGHTNING_ENERGY:
        return -20.0, "bellibolt_engine:non_lightning"
    if target_cid not in _IONO_LINE:
        return -20.0, "bellibolt_engine:not_iono_pokemon"
    if target_energy is None:
        target_energy = _get_target_energy_count(target_cid, state)
    score, reason = _score_attach_core(target_cid, state, target_energy, "bellibolt_engine")
    score += 30.0
    reason += "|bellibolt_engine:ability_attach_bonus"
    return score, reason


# -- Setup scoring functions ---------------------------------------------------

def _score_poffin_use(state: dict) -> tuple:
    """Score playing Buddy-Buddy Poffin based on bench/setup state."""
    f = _setup_missing_flags(state)
    score = 0.0
    parts: list = []

    if f["bench_count"] >= 5:
        return -30.0, "poffin_bench_full"

    if f["bench_count"] == 0:
        score += 120.0; parts.append("poffin_empty_bench")
    elif f["bench_count"] == 1:
        score += 90.0;  parts.append("poffin_low_bench")
    elif f["bench_count"] == 2:
        score += 45.0;  parts.append("poffin_medium_bench")

    if not f["has_tadbulb"]:  score += 60.0; parts.append("missing_tadbulb")
    if not f["has_voltorb"]:  score += 55.0; parts.append("missing_voltorb")
    if not f["has_wattrel"]:  score += 35.0; parts.append("missing_wattrel")

    if f["energy_in_hand"] >= 4:
        score += 30.0; parts.append("energy_flood_need_setup")

    if _count_in_hand(state, _BELLIBOLT_EX) > 0 and not f["has_tadbulb"]:
        score += 40.0; parts.append("bellibolt_in_hand_need_tadbulb")
    if _count_in_hand(state, _KILOWATTREL) > 0 and not f["has_wattrel"]:
        score += 35.0; parts.append("kilowattrel_in_hand_need_wattrel")

    if score <= 0:
        return 0.0, ""
    return score, "|".join(parts)


def _score_poffin_bench(cid: str, state: dict) -> tuple:
    """Bench fetch order for Poffin/TO_BENCH: spread Tadbulb/Voltorb/Wattrel."""
    if _bench_size(state) >= 5:
        return -30.0, "bench_full"

    active      = _active_cid(state)
    tadbulb_cnt = _count_own(state, _TADBULB)
    voltorb_cnt = _count_own(state, _VOLTORB)
    wattrel_cnt = _count_own(state, _WATTREL)
    has_bellibolt_hand   = _count_in_hand(state, _BELLIBOLT_EX) > 0
    has_kilowattrel_hand = _count_in_hand(state, _KILOWATTREL)  > 0

    # Active is Tadbulb → Voltorb/Wattrel on bench first
    if active == _TADBULB:
        if cid == _VOLTORB and voltorb_cnt == 0:
            return 160.0, "poffin_first_voltorb_active_tadbulb"
        if cid == _WATTREL and wattrel_cnt == 0:
            if has_kilowattrel_hand:
                return 150.0, "poffin_first_wattrel_active_tadbulb_with_kilowattrel"
            return 125.0, "poffin_first_wattrel_active_tadbulb"
        if cid == _TADBULB and tadbulb_cnt >= 1:
            return 25.0, "poffin_extra_tadbulb_low_priority"

    # Active is Voltorb → Tadbulb first
    if active == _VOLTORB:
        if cid == _TADBULB and tadbulb_cnt == 0:
            if has_bellibolt_hand:
                return 170.0, "poffin_first_tadbulb_active_voltorb_with_bellibolt"
            return 150.0, "poffin_first_tadbulb_active_voltorb"
        if cid == _WATTREL and wattrel_cnt == 0:
            return 115.0, "poffin_first_wattrel_active_voltorb"

    # Active is Wattrel → Tadbulb then Voltorb
    if active == _WATTREL:
        if cid == _TADBULB and tadbulb_cnt == 0:
            return 155.0, "poffin_first_tadbulb_active_wattrel"
        if cid == _VOLTORB and voltorb_cnt == 0:
            return 145.0, "poffin_first_voltorb_active_wattrel"

    # Default priority
    if cid == _TADBULB:
        if tadbulb_cnt == 0:
            return (165.0, "poffin_first_tadbulb_with_bellibolt") if has_bellibolt_hand \
                else (145.0, "poffin_first_tadbulb")
        if tadbulb_cnt == 1: return 55.0, "poffin_second_tadbulb"
        return 10.0, "poffin_extra_tadbulb"

    if cid == _VOLTORB:
        if voltorb_cnt == 0: return 150.0, "poffin_first_voltorb"
        if voltorb_cnt == 1: return  45.0, "poffin_second_voltorb"
        return 10.0, "poffin_extra_voltorb"

    if cid == _WATTREL:
        if wattrel_cnt == 0:
            return (140.0, "poffin_first_wattrel_with_kilowattrel") if has_kilowattrel_hand \
                else (110.0, "poffin_first_wattrel")
        if wattrel_cnt == 1: return 35.0, "poffin_second_wattrel"
        return 10.0, "poffin_extra_wattrel"

    return 0.0, ""


def _score_play_iono_basic(cid: str, state: dict) -> tuple:
    """Score playing an Iono's basic Pokémon from hand to bench."""
    if cid not in IONO_BASIC_IDS:
        return 0.0, ""
    bench_count = _bench_size(state)
    if bench_count >= 5:
        return -30.0, "bench_full"

    tadbulb_cnt = _count_own(state, _TADBULB)
    voltorb_cnt = _count_own(state, _VOLTORB)
    wattrel_cnt = _count_own(state, _WATTREL)

    if bench_count == 0:
        if cid == _TADBULB: return 130.0, "play_basic_empty_bench_tadbulb"
        if cid == _VOLTORB: return 125.0, "play_basic_empty_bench_voltorb"
        if cid == _WATTREL: return 105.0, "play_basic_empty_bench_wattrel"

    if bench_count == 1:
        if cid == _TADBULB and tadbulb_cnt == 0: return 120.0, "play_basic_second_setup_tadbulb"
        if cid == _VOLTORB and voltorb_cnt == 0: return 115.0, "play_basic_second_setup_voltorb"
        if cid == _WATTREL and wattrel_cnt == 0: return 100.0, "play_basic_second_setup_wattrel"

    if cid == _TADBULB and tadbulb_cnt == 0: return 100.0, "play_missing_tadbulb"
    if cid == _VOLTORB and voltorb_cnt == 0: return  95.0, "play_missing_voltorb"
    if cid == _WATTREL and wattrel_cnt == 0: return  80.0, "play_missing_wattrel"
    if cid == _TADBULB and tadbulb_cnt == 1: return  35.0, "play_second_tadbulb"
    if cid == _VOLTORB and voltorb_cnt == 1: return  35.0, "play_second_voltorb"
    if cid == _WATTREL and wattrel_cnt == 1: return  25.0, "play_second_wattrel"
    return 5.0, "play_extra_iono_basic"


def _score_setup_support_use(cid: str, state: dict) -> tuple:
    """Score Lillie / Canari / Levincia as setup-deficit supporters."""
    f          = _setup_missing_flags(state)
    setup_poor = _is_setup_poor(state)
    score = 0.0
    parts: list = []

    if cid == _LILLIES:
        if setup_poor:                                  score += 75.0; parts.append("lillie_setup_poor")
        if f["energy_in_hand"] >= 4:                   score += 45.0; parts.append("lillie_energy_flood")
        if f["energy_in_hand"] >= 5:                   score += 25.0; parts.append("lillie_very_energy_flood")
        if not f["has_tadbulb"] or not f["has_voltorb"]:
                                                        score += 30.0; parts.append("lillie_missing_core_basic")

    elif cid == _CANARI:
        sc, reason = _score_canari_use(state)
        return sc, reason

    elif cid == _LEVINCIA:
        if setup_poor:               score += 55.0; parts.append("levincia_setup_poor")
        if not f["has_tadbulb"]:     score += 25.0; parts.append("levincia_missing_tadbulb")
        if not f["has_voltorb"]:     score += 25.0; parts.append("levincia_missing_voltorb")
        if f["energy_in_hand"] >= 4: score += 20.0; parts.append("levincia_energy_flood_support")

    if score <= 0:
        return 0.0, ""
    return score, "|".join(parts)


# -- Board status helpers (for Canari / Ultra Ball search evaluation) --------

def _get_iono_board_status(state: dict) -> dict:
    """Return counts of each Iono's Pokemon in play and in hand."""
    return {
        "voltorb_in_play":      _count_own(state, _VOLTORB),
        "tadbulb_in_play":      _count_own(state, _TADBULB),
        "bellibolt_in_play":    _count_own(state, _BELLIBOLT_EX),
        "wattrel_in_play":      _count_own(state, _WATTREL),
        "kilowattrel_in_play":  _count_own(state, _KILOWATTREL),
        "voltorb_in_hand":      _count_in_hand(state, _VOLTORB),
        "tadbulb_in_hand":      _count_in_hand(state, _TADBULB),
        "bellibolt_in_hand":    _count_in_hand(state, _BELLIBOLT_EX),
        "wattrel_in_hand":      _count_in_hand(state, _WATTREL),
        "kilowattrel_in_hand":  _count_in_hand(state, _KILOWATTREL),
        "bench_count":          _bench_size(state),
        "bench_space_left":     max(0, 5 - _bench_size(state)),
    }


def _get_missing_iono_roles(state: dict) -> dict:
    """Determine which roles are missing from the current board."""
    s = _get_iono_board_status(state)
    missing = {
        "need_attacker":     s["voltorb_in_play"] == 0,
        "need_voltorb":      s["voltorb_in_play"] == 0,
        "need_tadbulb":      s["tadbulb_in_play"] == 0,
        "need_bellibolt":    s["tadbulb_in_play"] > 0 and s["bellibolt_in_play"] == 0,
        "need_wattrel":      s["wattrel_in_play"] == 0,
        "need_kilowattrel":  s["wattrel_in_play"] > 0 and s["kilowattrel_in_play"] == 0,
        "need_basic":        (s["voltorb_in_play"] + s["tadbulb_in_play"] + s["wattrel_in_play"]) <= 1,
        "need_evolution":    (s["tadbulb_in_play"] > 0 and s["bellibolt_in_play"] == 0)
                             or (s["wattrel_in_play"] > 0 and s["kilowattrel_in_play"] == 0),
    }
    return missing


# -- Bellibolt ex 2nd-body evaluation -----------------------------------------

def _active_bellibolt_is_damaged(state: dict) -> bool:
    """True if Bellibolt ex is active and has taken significant damage."""
    if _active_cid(state) != _BELLIBOLT_EX:
        return False
    active = state.get("active_pokemon") or {}
    hp   = active.get("hp_remaining", 9999)
    mhp  = active.get("max_hp", 280) or 280
    return (mhp - hp) >= 160


def _should_prepare_second_bellibolt(state: dict) -> bool:
    """True when the board justifies preparing a 2nd Bellibolt ex."""
    s = _get_iono_board_status(state)
    if s["bellibolt_in_play"] == 0:
        return False
    if s["tadbulb_in_play"] < 1:
        return False
    reasons = 0
    if _energy_in_hand_count(state) >= 3:
        reasons += 1
    if _active_bellibolt_is_damaged(state):
        reasons += 1
    if s["voltorb_in_play"] >= 1 and (s["wattrel_in_play"] >= 1 or s["kilowattrel_in_play"] >= 1):
        reasons += 1
    if s["bench_space_left"] >= 2:
        reasons += 1
    return reasons >= 2


def _score_bellibolt_search_target(cid: str, state: dict) -> tuple:
    """Shared search-target scoring for Bellibolt ex (used by Canari & Ultra Ball)."""
    if cid != _BELLIBOLT_EX:
        return 0.0, ""
    s = _get_iono_board_status(state)
    score = 0.0
    parts: list = []

    if s["tadbulb_in_play"] == 0:
        return -120.0, "search_avoid_bellibolt_without_tadbulb"

    if s["bellibolt_in_play"] == 0:
        score += 220.0
        parts.append("search_first_bellibolt_engine")
    else:
        score -= 90.0
        parts.append("search_second_bellibolt_low_priority")
        if _should_prepare_second_bellibolt(state):
            score += 100.0
            parts.append("search_second_bellibolt_needed")

    if s["bellibolt_in_hand"] >= 1:
        score -= 90.0
        parts.append("search_duplicate_bellibolt_in_hand")

    return score, "|".join(parts)


# -- Canari / Ultra Ball: usage and search-target scoring --------------------

def _score_canari_use(state: dict) -> tuple:
    """Score playing Canari (Supporter: search up to 4 Lightning Pokemon)."""
    m = _get_missing_iono_roles(state)
    score = 0.0
    parts: list = []

    if m["need_basic"]:        score += 80.0; parts.append("canari_use_need_basic")
    if m["need_attacker"]:     score += 70.0; parts.append("canari_use_need_attacker")
    if m["need_evolution"]:    score += 60.0; parts.append("canari_use_need_evolution")
    if m["need_tadbulb"] or m["need_voltorb"]:
                               score += 70.0; parts.append("canari_use_missing_core_piece")

    if score <= 0:
        return -20.0, "canari_low_value"
    return score, "|".join(parts)


def _score_canari_search_target(cid: str, state: dict) -> tuple:
    """Score which Pokemon to fetch when Canari resolves (ctx=TO_HAND)."""
    s = _get_iono_board_status(state)

    if cid == _BELLIBOLT_EX:
        return _score_bellibolt_search_target(cid, state)

    if cid == _KILOWATTREL:
        if s["wattrel_in_play"] > 0 and s["kilowattrel_in_play"] == 0:
            return 160.0, "canari_kilowattrel_for_wattrel_in_play"
        if s["wattrel_in_play"] == 0:
            return -70.0, "canari_avoid_kilowattrel_without_wattrel"
        if s["kilowattrel_in_hand"] > 0:
            return -50.0, "canari_avoid_duplicate_kilowattrel_in_hand"
        return 45.0, "canari_extra_kilowattrel_low_priority"

    if cid == _VOLTORB:
        if s["voltorb_in_play"] == 0:
            return 170.0, "canari_missing_voltorb_attacker"
        if s["voltorb_in_play"] == 1 and s["voltorb_in_hand"] == 0:
            return 70.0, "canari_second_voltorb_backup"
        return 15.0, "canari_extra_voltorb_low_priority"

    if cid == _TADBULB:
        if s["tadbulb_in_play"] == 0:
            return 175.0, "canari_missing_tadbulb_base"
        if s["tadbulb_in_play"] == 1 and s["tadbulb_in_hand"] == 0:
            return 65.0, "canari_second_tadbulb_backup"
        return 15.0, "canari_extra_tadbulb_low_priority"

    if cid == _WATTREL:
        if s["wattrel_in_play"] == 0:
            return 130.0, "canari_missing_wattrel_base"
        if s["wattrel_in_play"] == 1 and s["wattrel_in_hand"] == 0:
            return 45.0, "canari_second_wattrel_backup"
        return 10.0, "canari_extra_wattrel_low_priority"

    return 0.0, ""


def _score_ultra_ball_use(state: dict) -> tuple:
    """Score playing Ultra Ball (discard 2 → search any Pokemon)."""
    m = _get_missing_iono_roles(state)
    f = _setup_missing_flags(state)
    score = 0.0
    parts: list = []

    if m["need_bellibolt"]:    score += 80.0; parts.append("ultra_ball_use_need_bellibolt")
    if m["need_kilowattrel"]:  score += 60.0; parts.append("ultra_ball_use_need_kilowattrel")
    if m["need_attacker"]:     score += 60.0; parts.append("ultra_ball_use_need_attacker")
    if m["need_basic"]:        score += 50.0; parts.append("ultra_ball_use_need_basic")
    if f["energy_in_hand"] >= 4:
                               score += 45.0; parts.append("ultra_ball_energy_flood_discard_energy")

    if score <= 0:
        return -30.0, "ultra_ball_low_value_due_to_discard_cost"
    return score, "|".join(parts)


def _score_ultra_ball_search_target(cid: str, state: dict) -> tuple:
    """Score which Pokemon to fetch when Ultra Ball / search resolves (ctx=TO_HAND)."""
    s = _get_iono_board_status(state)

    if cid == _BELLIBOLT_EX:
        return _score_bellibolt_search_target(cid, state)

    if cid == _KILOWATTREL:
        if s["wattrel_in_play"] > 0 and s["kilowattrel_in_play"] == 0:
            return 170.0, "ultra_ball_kilowattrel_for_wattrel"
        if s["wattrel_in_play"] == 0:
            return -90.0, "ultra_ball_avoid_kilowattrel_without_wattrel"
        if s["kilowattrel_in_hand"] > 0:
            return -70.0, "ultra_ball_avoid_duplicate_kilowattrel"
        return 35.0, "ultra_ball_extra_kilowattrel_low_priority"

    if cid == _VOLTORB:
        if s["voltorb_in_play"] == 0:
            return 180.0, "ultra_ball_missing_voltorb_attacker"
        if s["voltorb_in_play"] == 1 and s["voltorb_in_hand"] == 0:
            return 55.0, "ultra_ball_second_voltorb_backup"
        return 10.0, "ultra_ball_extra_voltorb_low_priority"

    if cid == _TADBULB:
        if s["tadbulb_in_play"] == 0:
            return 170.0, "ultra_ball_missing_tadbulb_base"
        if s["tadbulb_in_play"] == 1 and s["tadbulb_in_hand"] == 0:
            return 50.0, "ultra_ball_second_tadbulb_backup"
        return 10.0, "ultra_ball_extra_tadbulb_low_priority"

    if cid == _WATTREL:
        if s["wattrel_in_play"] == 0:
            return 130.0, "ultra_ball_missing_wattrel_base"
        if s["wattrel_in_play"] == 1 and s["wattrel_in_hand"] == 0:
            return 35.0, "ultra_ball_second_wattrel_backup"
        return 8.0, "ultra_ball_extra_wattrel_low_priority"

    return 0.0, ""


# -- Voltorb attack scoring ----------------------------------------------------

def score_voltorb_attack(opt: dict, state: dict, select=None) -> tuple:
    """
    Score Voltorb attack based on damage scaling from Lightning on Iono's Pokemon.

    Voltorb damage = 20 + 20 * (total Lightning on all Iono's Pokemon).
    Gives large bonus so attack is preferred over End/Retreat/optional Ability.
    """
    if not _is_attack(opt):
        return 0.0, ""

    if _active_cid(state) != _VOLTORB:
        return 0.0, ""

    damage    = _estimate_voltorb_damage(state)
    lightning = _count_lightning_on_iono_pokemon(state)

    score = 180.0
    parts: list = ["voltorb_legal_attack"]

    score += damage * 0.8
    parts.append("voltorb_scaling_damage")

    if lightning >= 3:
        score += 40.0
        parts.append("voltorb_good_energy_count")
    if lightning >= 4:
        score += 70.0
        parts.append("voltorb_high_energy_count")
    if lightning >= 5:
        score += 100.0
        parts.append("voltorb_very_high_energy_count")

    opp_hp = state.get("opponent", {}).get("active_pokemon", {}).get("hp_remaining", 9999)
    if damage >= opp_hp > 0:
        score += 1000.0
        parts.append("voltorb_can_ko")

    return score, "|".join(parts)


def score_voltorb_safety_penalty(opt: dict, state: dict, select=None) -> tuple:
    """
    Penalise End / Retreat / optional Ability when Voltorb is active and
    a legal attack is available.
    """
    if _active_cid(state) != _VOLTORB:
        return 0.0, ""

    has_attack = False
    if select is not None:
        try:
            from agent.turn_rule_engine import has_legal_attack_option as _hla
            has_attack = _hla(select)
        except Exception:
            pass

    if not has_attack:
        return 0.0, ""

    if _is_end(opt):
        return -1000.0, "voltorb_avoid_end_when_attack_available"
    if _is_retreat(opt):
        return -1000.0, "voltorb_avoid_retreat_when_attack_available"
    if _is_ability(opt):
        return -80.0, "voltorb_attack_available_avoid_optional_ability"

    return 0.0, ""


# -- Kilowattrel Ability scoring -----------------------------------------------

def score_kilowattrel_ability(opt: dict, state: dict, select=None) -> tuple:
    """
    Score Iono's Kilowattrel Ability: discard 1 attached basic Lightning → draw to 6.

    Only applies when Kilowattrel (271) is the Pokemon using the ability.
    High value when: hand is small, can't attack, setup is weak.
    Penalised when: can attack now, discarding would break attack-ready state,
                    hand is already large, or energy is too low to risk discarding.
    """
    if not _is_ability(opt):
        return 0.0, ""

    cid = str(opt.get("resolved_card_id") or "")
    if cid != _KILOWATTREL:
        return 0.0, ""

    # Use active Pokemon's energy count (ability operates on the active Pokemon)
    active_energy = _active_energy_count(state)
    hand_count    = state.get("hand_count", 0) or len(state.get("hand") or [])

    # Check whether an attack option currently exists
    has_attack = False
    if select is not None:
        try:
            from agent.turn_rule_engine import has_legal_attack_option as _hla
            has_attack = _hla(select)
        except Exception:
            pass

    # Kilowattrel attack: LCC = 3 total energy
    can_attack_now           = active_energy >= _KILOWATTREL_ATTACK_ENERGY_REQ
    # Ability discards 1 Lightning → effective energy drops by 1
    can_attack_after_discard = (active_energy - 1) >= _KILOWATTREL_ATTACK_ENERGY_REQ

    # --- Hard disqualifiers (negative scores, returned immediately) ---

    # Attack is offered AND Kilowattrel can attack → always prefer attack
    if has_attack and can_attack_now:
        return -250.0, "kilowattrel_avoid_ability_when_attack_available"

    # Ability would destroy the attack-ready state
    if can_attack_now and not can_attack_after_discard:
        return -300.0, "kilowattrel_ability_breaks_attack_ready_state"

    # Hand is large enough — draw has low marginal value, and we lose an energy
    if hand_count >= 5:
        return -120.0, "kilowattrel_avoid_ability_with_large_hand"

    # --- Positive conditions ---
    score = 0.0
    parts: list = []

    if hand_count == 4:
        score += 10.0
        parts.append("kilowattrel_ability_medium_hand")

    if hand_count <= 3:
        score += 80.0
        parts.append("kilowattrel_ability_low_hand")

    if hand_count <= 2:
        score += 50.0
        parts.append("kilowattrel_ability_very_low_hand")

    if _is_setup_poor(state):
        score += 50.0
        parts.append("kilowattrel_ability_setup_poor")

    if not has_attack:
        score += 30.0
        parts.append("kilowattrel_ability_no_attack_available")

    # Discarding when energy is already very low is risky
    if active_energy <= 1:
        score -= 80.0
        parts.append("kilowattrel_ability_energy_too_low")

    if score <= 0:
        return score, "|".join(parts) if parts else "kilowattrel_ability_low_value"
    return score, "|".join(parts)


# -- Main entry point ----------------------------------------------------------

def score_bonus(action: dict, state: dict, knowledge=None) -> tuple:
    """
    Return (bonus, reason) for Iono's Kilowattrel deck-specific actions.
    bonus is ADDED to the base policy score; negative = discourage.
    """
    opt_type = action.get("type")
    cid      = str(action.get("resolved_card_id") or action.get("cardId") or "")
    ctx      = action.get("select_context")

    # -- 1. Evolve Tadbulb -> Bellibolt ex ------------------------------------
    if opt_type == 9 and cid == _BELLIBOLT_EX:
        s = _get_iono_board_status(state)
        if s["bellibolt_in_play"] == 0:
            return 220.0, "ionos:evolve_first_bellibolt_engine"
        score_e = -60.0
        if _should_prepare_second_bellibolt(state):
            score_e += 80.0
        return score_e, "ionos:evolve_second_bellibolt"

    # -- 2. Evolve Wattrel -> Kilowattrel -------------------------------------
    if opt_type == 9 and cid == _KILOWATTREL:
        return 7.0, "ionos:evolve_kilowattrel"

    # -- 3. Attack with Voltorb -----------------------------------------------
    if _is_attack(action) and _active_cid(state) == _VOLTORB:
        energy = _active_energy_count(state)
        if energy >= _VOLTORB_ATTACK_ENERGY_REQ:
            est_damage   = _estimate_voltorb_damage(state)
            damage_bonus = min(8.0, est_damage * 0.04)
            return 5.0 + damage_bonus, "ionos:voltorb_attack"

    # -- 4. Attack with Bellibolt ex (official: LLLC = 4 energy, fixed 230) ------
    if _is_attack(action) and _active_cid(state) == _BELLIBOLT_EX:
        energy = _active_energy_count(state)
        if energy >= _BELLIBOLT_ATTACK_ENERGY_REQ:
            return 23.0, "ionos:bellibolt_ex_attack"

    # -- 5. Attack with Kilowattrel -------------------------------------------
    if _is_attack(action) and _active_cid(state) == _KILOWATTREL:
        energy = _active_energy_count(state)
        if energy >= _KILOWATTREL_ATTACK_ENERGY_REQ:
            return 6.0, "ionos:kilowattrel_attack"

    # -- 6. Bellibolt ex Ability — energy acceleration (Active or Bench) ------
    if _is_ability(action) and cid == _BELLIBOLT_EX:
        hand           = [str(c) for c in (state.get("hand") or [])]
        energy_in_hand = hand.count(_LIGHTNING_ENERGY)
        if energy_in_hand > 0:
            bellibolt_energy = _get_target_energy_count(_BELLIBOLT_EX, state)
            if bellibolt_energy < _BELLIBOLT_ATTACK_ENERGY_REQ:
                # Ability charges Bellibolt toward attack threshold (LLLC = 4)
                return 250.0, "ionos:bellibolt_ability_charge_for_attack"
            else:
                # Bellibolt ready; ability still useful for Voltorb scaling
                return 30.0, "ionos:bellibolt_ability_voltorb_scaling"
        return 4.0, "ionos:bellibolt_ability_no_energy"

    # -- 7. ATTACH (opt_type=8) — energy × target scoring --------------------
    if opt_type == 8:
        e_cid       = str(action.get("resolved_card_id") or "")
        target_area = action.get("inPlayArea")
        target_idx  = action.get("inPlayIndex")

        is_tool = knowledge is not None and (
            knowledge.get_role(e_cid) == "tool" or knowledge.has_tag(e_cid, "tool")
        )

        if target_area == _AREA_ACTIVE:
            t_mon   = state.get("active_pokemon") or {}
            t_cid   = _active_cid(state)
            t_energy = t_mon.get("energy_count", 0)
        elif target_area == _AREA_BENCH and target_idx is not None:
            bench    = state.get("bench") or []
            t_mon    = bench[target_idx] if target_idx < len(bench) else {}
            t_cid    = str(t_mon.get("card_id", ""))
            t_energy = t_mon.get("energy_count", 0)
        else:
            t_cid    = ""
            t_energy = 0

        if is_tool:
            tsc, treason = _score_tool_attachment_bonus(e_cid, t_cid, state)
            return tsc, f"ionos:attach_tool|{treason}"

        if e_cid and t_cid:
            # Engine mode: Bellibolt on field (active or bench) → ability-aware priority
            if _bellibolt_on_field(state):
                esc, ereason = score_bellibolt_energy_attach(e_cid, t_cid, state, t_energy)
            else:
                esc, ereason = score_energy_attachment(e_cid, t_cid, state, t_energy)
            if ereason:
                return esc, f"ionos:attach_energy|{ereason}"

    # -- 8-10. Play Iono's basic Pokémon from hand ----------------------------
    if opt_type == 7 and cid in IONO_BASIC_IDS:
        sc, reason = _score_play_iono_basic(cid, state)
        if sc != 0.0:
            return sc, f"ionos:{reason}"

    # -- 11. Buddy-Buddy Poffin (PLAY decision) --------------------------------
    if opt_type == 7 and cid == _BUDDYS_POFFIN:
        sc, reason = _score_poffin_use(state)
        if sc != 0.0:
            return sc, f"ionos:{reason}"
        return 0.0, ""

    # -- 11b. TO_BENCH / SETUP_BENCH context — which Pokemon to place ----------
    if ctx in (2, 5) and cid in (_TADBULB, _VOLTORB, _WATTREL):
        sc, reason = _score_poffin_bench(cid, state)
        if sc > 0.0:
            return sc, f"ionos:{reason}"

    # -- 11c. Ultra Ball (PLAY decision) -------------------------------------
    if opt_type == 7 and cid == _ULTRA_BALL:
        sc, reason = _score_ultra_ball_use(state)
        if sc != 0.0:
            return sc, f"ionos:{reason}"

    # -- 12. Energy Retrieval — value scales with hand energy shortage ---------
    if opt_type == 7 and cid == _ENERGY_RETRIEVAL:
        hand           = [str(c) for c in (state.get("hand") or [])]
        energy_in_hand = hand.count(_LIGHTNING_ENERGY)
        if energy_in_hand == 0:
            return 5.0, "ionos:energy_retrieval_no_energy_in_hand"
        return 2.0, "ionos:energy_retrieval"

    # -- 13. TO_HAND context — search priority --------------------------------
    if ctx == 7:   # SelectContext.TO_HAND
        if cid in IONO_POKEMON_IDS:
            # Use Canari-specific scoring when Canari was the source
            sc_c, reason_c = _score_canari_search_target(cid, state)
            sc_u, reason_u = _score_ultra_ball_search_target(cid, state)
            # Pick the more impactful signal (both share the "missing role" logic)
            if abs(sc_c) >= abs(sc_u):
                sc, reason = sc_c, reason_c
            else:
                sc, reason = sc_u, reason_u
            return sc, f"ionos:{reason}"

    # -- 14. EVOLVES_TO context (ctx=19) --------------------------------------
    if ctx == 19:
        if cid == _BELLIBOLT_EX:
            return 5.0, "ionos:evolves_to_bellibolt"
        if cid == _KILOWATTREL:
            return 3.0, "ionos:evolves_to_kilowattrel"

    # -- 15. SETUP_ACTIVE (ctx=1) — initial Active Pokemon priority -----------
    if ctx == 1:
        if cid == _VOLTORB:
            return 30.0, "ionos:start_voltorb"
        if cid == _WATTREL:
            return 15.0, "ionos:start_wattrel"
        if cid == _TADBULB:
            return 10.0, "ionos:start_tadbulb"
        if cid in (_BELLIBOLT_EX, _KILOWATTREL):
            return -10.0, "ionos:avoid_evolved_start"

    # -- 16. Lillie / Canari / Levincia — setup support ----------------------
    if opt_type == 7 and cid in (_LILLIES, _CANARI, _LEVINCIA):
        # Hard stop for Lillie: don't discard ready evolution combos
        if cid == _LILLIES:
            hand       = [str(c) for c in (state.get("hand") or [])]
            hand_set   = set(hand)
            setup_poor = _is_setup_poor(state)
            # When board is thin, setup recovery > keeping evolution cards in hand
            if not setup_poor:
                if _BELLIBOLT_EX in hand_set and _tadbulb_on_field(state):
                    return -8.0, "ionos:lillies_keep_bellibolt"
                if _KILOWATTREL in hand_set and _wattrel_on_field(state):
                    return -6.0, "ionos:lillies_keep_kilowattrel"
        sc, reason = _score_setup_support_use(cid, state)
        if sc != 0.0:
            return sc, f"ionos:{reason}"

    # -- 17b. RETREAT (type=12) — suppress when attacker can already attack ----
    if _is_retreat(action):
        active_cid    = _active_cid(state)
        active_energy = _active_energy_count(state)
        if active_cid == _BELLIBOLT_EX and active_energy >= _BELLIBOLT_ATTACK_ENERGY_REQ:
            return -700.0, "ionos:avoid_retreat_bellibolt_can_attack"
        if active_cid == _VOLTORB and active_energy >= _VOLTORB_ATTACK_ENERGY_REQ:
            return -300.0, "ionos:avoid_retreat_voltorb_can_attack"
        if active_cid == _KILOWATTREL and active_energy >= _KILOWATTREL_ATTACK_ENERGY_REQ:
            return -300.0, "ionos:avoid_retreat_kilowattrel_can_attack"

    # -- 17. Night Stretcher ---------------------------------------------------
    if opt_type == 7 and cid == _NIGHT_STRETCHER:
        return 2.0, "ionos:night_stretcher"

    return 0.0, ""


# ---------------------------------------------------------------------------
# Iono's-specific log builder
# ---------------------------------------------------------------------------

def build_ionos_log(state: dict, selected_action: dict) -> dict:
    """
    Build a deck-specific log entry for one action decision.
    Called from main.py and passed to GameLogger.log(deck_log=...).
    """
    lightning_count  = _count_lightning_on_iono_pokemon(state)
    voltorb_damage   = _estimate_voltorb_damage(state)
    bellibolt_active = _active_cid(state) == _BELLIBOLT_EX
    bellibolt_present = _bellibolt_on_field(state)

    log: dict = {
        "deck_name": "ionos_kilowattrel",
        "ionos_rules_enabled": True,
        "voltorb": {
            "iono_lightning_count":    lightning_count,
            "estimated_voltorb_damage": voltorb_damage,
        },
        "bellibolt": {
            "bellibolt_in_play":   bellibolt_present,
            "bellibolt_is_active": bellibolt_active,
        },
    }

    if selected_action:
        opt_type    = selected_action.get("type")
        sel_cid     = selected_action.get("resolved_card_id")
        sel_cname   = selected_action.get("resolved_card_name")
        log["action"] = {
            "selected_action_type": opt_type,
            "selected_card_id":     sel_cid,
            "selected_card_name":   sel_cname,
        }

        # Energy attach detail — only for ATTACH (opt_type=8) decisions
        if opt_type == 8:
            e_cid       = str(sel_cid or "")
            target_area = selected_action.get("inPlayArea")
            target_idx  = selected_action.get("inPlayIndex")

            if target_area == _AREA_ACTIVE:
                t_cid      = _active_cid(state)
                target_mon = state.get("active_pokemon") or {}
            elif target_area == _AREA_BENCH and target_idx is not None:
                bench      = state.get("bench") or []
                target_mon = bench[target_idx] if target_idx < len(bench) else {}
                t_cid      = str(target_mon.get("card_id", ""))
            else:
                t_cid      = ""
                target_mon = {}

            t_energy = target_mon.get("energy_count", 0) if isinstance(target_mon, dict) else 0

            if bellibolt_active or _bellibolt_on_field(state):
                esc, ereason = score_bellibolt_energy_attach(e_cid, t_cid, state, t_energy)
                mode = "bellibolt_engine"
            else:
                esc, ereason = score_energy_attachment(e_cid, t_cid, state, t_energy)
                mode = "normal"

            log["energy_attach"] = {
                "energy_card_id":            e_cid,
                "target_card_id":            t_cid,
                "target_energy_count_before": t_energy,
                "is_iono_pokemon":           t_cid in _IONO_LINE,
                "score_energy_attachment":   esc,
                "energy_attach_reason":      ereason,
                "scoring_mode":              mode,
                "increases_voltorb_damage":  t_cid in _IONO_LINE and e_cid == _LIGHTNING_ENERGY,
            }

    return log
