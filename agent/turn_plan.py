"""
Turn plan computation.

compute_plan(obs, card_table, attack_full) -> TurnPlan

TurnPlan fields used by policy.py:
  has_plan                 : bool        — True when a concrete plan exists
  goal                     : str         — human-readable description
  need_boss / need_energy / need_switch  — type of pre-attack action required
  target_card_id           : int | None  — card ID of the planned KO target
  target_serial            : int | None  — serial for disambiguation
  target_zone              : str | None  — "active" or "bench"
  target_active            : bool        — True if target is already in Active
  planned_attack_id        : int | None  — attackId to use
  ko_expected              : bool        — planned attack KOs the target
  pre_attack_requirements  : list[str]   — ordered steps before attacking
                                           e.g. ["boss"], ["switch", "energy"]
  attacker_active / attacker_idx        — which of our Pokemon will attack

Attacker filtering
------------------
Setup Pokemon (Tadbulb, Wattrel — pure evolution bases) are NOT planned as
attackers unless they can actually KO the target this turn.
Voltorb (265), Bellibolt ex (269), and Kilowattrel (271) are planned attackers.
"""

# Card IDs of setup Pokemon that should not be treated as primary attackers
# unless their attack produces a KO.
_SETUP_MON_IDS = {268, 270}  # Iono's Tadbulb, Iono's Wattrel (pure evolution bases)

# Card IDs that are planned as attackers.
_ATTACKER_IDS = {265, 269, 271}  # Voltorb, Bellibolt ex, Kilowattrel

# Deck-specific fallback energy requirements per attacker card ID.
# The game's legal-move list is the primary source; these are used only when
# the planner has to estimate feasibility before legal moves are checked.
_ATTACK_REQUIREMENTS = {
    265: {
        "name": "Iono's Voltorb",
        "required_total_energy": 2,
        "required_lightning_energy": 0,
        "role": "early_main_attacker",
    },
    269: {
        "name": "Iono's Bellibolt ex",
        "required_total_energy": 4,   # official: LLLC
        "required_lightning_energy": 3,
        "role": "engine_attacker",
    },
    271: {
        "name": "Iono's Kilowattrel",
        "required_total_energy": 3,
        "required_lightning_energy": 1,
        "role": "sub_attacker",
    },
}

from dataclasses import dataclass, field


@dataclass
class TurnPlan:
    """Strategic plan for the current turn."""
    has_plan: bool = False
    goal:     str  = ""

    # Pre-attack setup flags
    need_boss:   bool = False
    need_energy: bool = False
    need_switch: bool = False
    need_evolve: bool = False
    need_heal:   bool = False

    # Planned target (opponent Pokemon to KO)
    target_card_id: int | None = None
    target_serial:  int | None = None
    target_zone:    str | None = None   # "active" or "bench"
    target_active:  bool       = True
    target_idx:     int        = 0      # bench index when target_active=False

    # Planned attack
    planned_attack_id: int | None = None
    ko_expected:       bool       = False

    # Ordered list of actions to complete BEFORE attacking.
    # policy._has_unresolved_pre_attack iterates this to decide suppression.
    pre_attack_requirements: list = field(default_factory=list)  # list[str]

    # Our attacker position (used by _score_attach_energy)
    attacker_active: bool = True
    attacker_idx:    int  = 0

    # Internal scoring value
    score: float = -1.0


_NULL_PLAN = TurnPlan()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_plan(obs, card_table: dict, attack_full: dict) -> TurnPlan:
    """
    Compute the best attack plan from a typed Observation.
    Returns _NULL_PLAN (has_plan=False) on any error or if no attack is viable.
    """
    try:
        return _compute(obs, card_table, attack_full)
    except Exception:
        return _NULL_PLAN


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _compute(obs, card_table: dict, attack_full: dict) -> TurnPlan:
    state   = obs.current
    my_idx  = int(state.yourIndex or 0)
    opp_idx = 1 - my_idx
    me      = state.players[my_idx]
    opp     = state.players[opp_idx]

    opp_prizes      = len(opp.prize)
    hand_energy     = _count_hand_energy(me.hand or [], card_table)
    energy_attached = bool(state.energyAttached)

    # Collect our Pokemon: (is_active, bench_idx, pokemon)
    my_mons = []
    for p in (me.active or []):
        if p is not None:
            my_mons.append((True, 0, p))
    for i, p in enumerate(me.bench or []):
        if p is not None:
            my_mons.append((False, i, p))

    # Collect opponent Pokemon: (is_active, bench_idx, pokemon)
    opp_mons = []
    for p in (opp.active or []):
        if p is not None:
            opp_mons.append((True, 0, p))
    for i, p in enumerate(opp.bench or []):
        if p is not None:
            opp_mons.append((False, i, p))

    if not opp_mons:
        return _NULL_PLAN

    best_plan  = _NULL_PLAN
    best_score = -1.0

    for my_active, my_i, my_mon in my_mons:
        c_me = card_table.get(my_mon.id)
        if c_me is None:
            continue
        my_type    = c_me.energyType
        cur_energy = len(my_mon.energies)

        # Setup Pokemon (Tadbulb / Wattrel) are valid attackers only if their
        # attack can KO the target.  Defer check to inner loop once damage known.
        is_setup_mon = int(my_mon.id) in _SETUP_MON_IDS

        for atk_id in (c_me.attacks or []):
            atk = attack_full.get(atk_id)
            if atk is None:
                continue

            _req_entry      = _ATTACK_REQUIREMENTS.get(int(my_mon.id))
            required        = (
                _req_entry["required_total_energy"] if isinstance(_req_entry, dict)
                else (_req_entry or (len(atk.energies) if atk.energies else 1))
            )
            can_now         = cur_energy >= required
            can_with_attach = (
                    not energy_attached
                    and hand_energy > 0
                    and cur_energy + 1 >= required
                )

            if not (can_now or can_with_attach):
                continue

            need_energy = can_with_attach and not can_now
            need_switch = not my_active

            for opp_active, opp_i, opp_mon in opp_mons:
                need_boss = not opp_active

                _mid = int(my_mon.id)
                if _mid == 265:
                    base = _voltorb_scaled_damage(me)
                elif _mid == 269:
                    base = _bellibolt_damage_estimate(me)
                else:
                    base = atk.damage
                damage = _calc_damage(base, my_type, opp_mon, card_table)
                prizes  = _prize_count(opp_mon, card_table)
                ko      = opp_mon.hp <= damage

                # Setup Pokemon only qualify as plan attackers when they KO.
                if is_setup_mon and not ko:
                    continue

                # Target value
                t_score  = prizes * 1000
                t_score += len(opp_mon.energies) * 150
                t_score += len(opp_mon.tools)    * 100
                c_opp = card_table.get(opp_mon.id)
                if c_opp:
                    if c_opp.stage2:  t_score += 250
                    elif c_opp.stage1: t_score += 130
                t_score += opp_mon.hp

                if not ko:
                    t_score = int(t_score * damage / max(1, opp_mon.hp))

                # Game-winning KO
                if ko and prizes >= opp_prizes:
                    t_score = 50_000

                pos_bonus  = (220 if my_active  else 0)
                pos_bonus += (300 if opp_active else 0)

                action_penalty  = (100 if need_switch else 0)
                action_penalty += (50  if need_boss   else 0)
                action_penalty += (10  if need_energy else 0)

                final = float(t_score + pos_bonus - action_penalty)

                if final > best_score:
                    best_score = final

                    # Build pre_attack_requirements in priority order
                    pre_reqs: list[str] = []
                    if need_boss:   pre_reqs.append("boss")
                    if need_switch: pre_reqs.append("switch")
                    if need_energy: pre_reqs.append("energy")

                    # Build human-readable goal
                    if ko and need_boss:
                        goal = "boss_bench_target_and_ko"
                    elif ko and need_switch:
                        goal = "switch_then_attack_ko"
                    elif ko:
                        goal = "attack_and_ko"
                    elif need_boss:
                        goal = "boss_bench_target"
                    elif need_switch:
                        goal = "switch_then_attack"
                    elif need_energy:
                        goal = "energy_then_attack"
                    else:
                        goal = "attack"

                    best_plan = TurnPlan(
                        has_plan           = True,
                        goal               = goal,
                        need_boss          = need_boss,
                        need_energy        = need_energy,
                        need_switch        = need_switch,
                        target_active      = opp_active,
                        target_idx         = opp_i,
                        target_card_id     = getattr(opp_mon, 'id',     None),
                        target_serial      = getattr(opp_mon, 'serial', None),
                        target_zone        = "active" if opp_active else "bench",
                        planned_attack_id  = atk_id,
                        ko_expected        = ko,
                        pre_attack_requirements = pre_reqs,
                        attacker_active    = my_active,
                        attacker_idx       = my_i,
                        score              = final,
                    )

    return best_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _voltorb_scaled_damage(me) -> int:
    """Voltorb damage: 20 + 20 × total Lightning energy on all Iono's Pokémon."""
    _IONO = {265, 268, 269, 270, 271}
    total = 0
    for p in list(me.active or []) + list(me.bench or []):
        if p is None or int(p.id) not in _IONO:
            continue
        for e in (p.energies or []):
            try:
                eid = int(e)
            except (TypeError, ValueError):
                val = getattr(e, "value", None)
                eid = int(val) if val is not None else None
            if eid == 4:  # Lightning
                total += 1
    return 20 + 20 * total


def _bellibolt_damage_estimate(me) -> int:
    """Bellibolt ex: official text Thunderous Bolt → fixed 230."""
    return 230


def _count_hand_energy(hand, card_table: dict) -> int:
    count = 0
    for card in hand:
        c = card_table.get(card.id)
        if c is not None and int(c.cardType) in (5, 6):  # BASIC_ENERGY, SPECIAL_ENERGY
            count += 1
    return count


def _calc_damage(base: int, my_type, opp_mon, card_table: dict) -> int:
    damage = base
    c = card_table.get(opp_mon.id)
    if c is None:
        return damage
    if c.weakness is not None and int(c.weakness) == int(my_type):
        damage *= 2
    if c.resistance is not None and int(c.resistance) == int(my_type):
        damage = max(0, damage - 30)
    return damage


def _prize_count(pokemon, card_table: dict) -> int:
    c = card_table.get(pokemon.id)
    if c is None:
        return 1
    if c.megaEx: return 3
    if c.ex:     return 2
    return 1
