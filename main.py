"""
Competition entry point — cabt (Card AI Battle) engine on kaggle-environments.
Uses cg.api for typed observation access.
"""
import os
import sys
import time

try:
    _agent_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _agent_dir = '/kaggle_simulations/agent'
sys.path.insert(0, _agent_dir)

from cg.api import all_card_data, to_observation_class, OptionType, AreaType
from agent.policy import PolicyAgent
from agent.logger import GameLogger
try:
    from agent.turn_plan import compute_plan as _compute_plan
except Exception:
    _compute_plan = None
try:
    from agent.ionos_rules import build_ionos_log as _build_ionos_log
except Exception:
    _build_ionos_log = None

# Load deck once at startup
file_path = os.path.join(_agent_dir, 'deck.csv')
if not os.path.exists(file_path):
    file_path = '/kaggle_simulations/agent/deck.csv'
try:
    with open(file_path) as _f:
        _DECK = [int(l.strip()) for l in _f if l.strip()]
except Exception:
    _DECK = []

# Load card metadata from cabt engine
try:
    _all_cards = all_card_data()
    card_table = {c.cardId: c for c in _all_cards}
except Exception:
    card_table = {}

_policy: PolicyAgent = None
_logger: GameLogger = None
_planner = None   # agent.planner.Planner; None if import fails
AGENT_VERSION = "v5"
DECK_NAME = "ionos_kilowattrel"

# Opponent card tracking — reset each game
_opp_seen: dict[int, set] = {}   # cardId -> set of event types seen ("play","attack","evolve")
_last_game_turn: int = -1         # used to detect a new game starting


def _init():
    global _policy, _logger, _planner
    _policy = PolicyAgent()
    _logger = GameLogger(deck_name=DECK_NAME, agent_version=AGENT_VERSION)
    try:
        from agent.planner import Planner
        from agent.opponent_model import OpponentModel
        opp_model = OpponentModel(_policy.knowledge, _policy._attack_data or {})
        _planner = Planner(
            _policy.knowledge,
            _policy.evaluator,
            opp_model,
            _policy._attack_data or {},
        )
    except Exception:
        _planner = None


# ──────────────────────────────────────────────────────────────
# Observation helpers
# ──────────────────────────────────────────────────────────────

_ENERGY_NAME_MAP = {
    "GRASS": 1, "FIRE": 2, "WATER": 3, "LIGHTNING": 4,
    "PSYCHIC": 5, "FIGHTING": 6, "DARKNESS": 7, "DARK": 7,
    "METAL": 8, "FAIRY": 9, "DRAGON": 10, "COLORLESS": 11,
}


def _resolve_energy_types(raw_energies: list) -> list:
    """Convert a raw energies list (EnergyType / int / dict / object) to list[int]."""
    result = []
    for e in raw_energies:
        eid = None
        if isinstance(e, int):
            eid = e
        elif isinstance(e, dict):
            raw = e.get("id") or e.get("card_id") or e.get("type")
            if raw is not None:
                try:
                    eid = int(raw)
                except (TypeError, ValueError):
                    pass
        else:
            try:
                eid = int(e)
            except Exception:
                val = getattr(e, "value", None)
                if val is not None:
                    try:
                        eid = int(val)
                    except (TypeError, ValueError):
                        pass
                if eid is None:
                    name = str(getattr(e, "name", "")).upper()
                    eid = _ENERGY_NAME_MAP.get(name)
        if eid is not None:
            result.append(int(eid))
    return result


def _normalize_pokemon(p) -> dict:
    """Convert a Pokemon dataclass (or legacy dict) to our internal snake_case format."""
    if p is None:
        return {}
    if isinstance(p, dict):
        raw_energies = p.get("energies") or []
        energy_types = _resolve_energy_types(raw_energies)
        raw_cards    = p.get("energyCards") or []
        energy_cards = [str(c.get("id", "") if isinstance(c, dict) else getattr(c, "id", ""))
                        for c in raw_cards if c is not None]
        result = {
            "card_id":      str(p.get("id", "")),
            "hp_remaining": p.get("hp", 0),
            "max_hp":       p.get("maxHp", 1) or 1,
            "energy_count": len(energy_types),
            "energies":     energy_types,
            "energy_types": energy_types,
            "energy_cards": energy_cards,
        }
    else:
        # Typed Pokemon dataclass from cg.api
        raw_energies = getattr(p, "energies", None) or []
        energy_types = _resolve_energy_types(raw_energies)
        raw_cards    = getattr(p, "energyCards", None) or []
        energy_cards = [str(getattr(c, "id", "")) for c in raw_cards if c is not None]
        result = {
            "card_id":      str(getattr(p, "id", "")),
            "hp_remaining": getattr(p, "hp", 0),
            "max_hp":       getattr(p, "maxHp", 1) or 1,
            "energy_count": len(energy_types),
            "energies":     energy_types,
            "energy_types": energy_types,
            "energy_cards": energy_cards,
        }
    try:
        from agent.card_metadata import enrich_pokemon
        enrich_pokemon(result)
    except Exception:
        pass
    return result


def _board_to_state(current) -> dict:
    """Convert obs.current (State dataclass or dict) to our internal state format."""
    if current is None:
        return {}

    if isinstance(current, dict):
        players     = current.get('players') or []
        your_index  = int(current.get('yourIndex') or 0)
        opp_index   = 1 - your_index
        me  = players[your_index] if your_index < len(players) and isinstance(players[your_index], dict) else {}
        opp = players[opp_index]  if opp_index  < len(players) and isinstance(players[opp_index],  dict) else {}

        me_active_raw  = next(iter(me.get('active')  or []), None)
        opp_active_raw = next(iter(opp.get('active') or []), None)
        prizes_left     = sum(1 for p in (me.get('prize')  or []) if p is None)
        opp_prizes_left = sum(1 for p in (opp.get('prize') or []) if p is None)
        me_hand_count   = me.get('handCount', 0)
        me_deck_count   = me.get('deckCount', 0)
        me_hand_ids     = []  # dict format doesn't expose hand card IDs
        me_bench        = [_normalize_pokemon(p) for p in (me.get('bench')  or [])]
        opp_bench       = [_normalize_pokemon(p) for p in (opp.get('bench') or [])]
        opp_deck_count  = opp.get('deckCount', 0)
        energy_attached = bool(current.get('energyAttached'))
        retreated       = bool(current.get('retreated'))
        supporter_played= bool(current.get('supporterPlayed'))
        turn            = int(current.get('turn') or 0)
    else:
        # Typed State dataclass
        players     = current.players or []
        your_index  = int(current.yourIndex or 0)
        opp_index   = 1 - your_index
        me  = players[your_index] if your_index < len(players) else None
        opp = players[opp_index]  if opp_index  < len(players) else None

        me_active_raw  = next(iter(me.active  or []), None) if me else None
        opp_active_raw = next(iter(opp.active or []), None) if opp else None
        prizes_left     = sum(1 for p in (me.prize  or []) if p is None) if me else 0
        opp_prizes_left = sum(1 for p in (opp.prize or []) if p is None) if opp else 0
        me_hand_count   = me.handCount  if me else 0
        me_deck_count   = me.deckCount  if me else 0
        me_hand_ids     = [str(c.id) for c in (me.hand or [])] if (me and me.hand is not None) else []
        me_bench        = [_normalize_pokemon(p) for p in (me.bench  or [])] if me else []
        opp_bench       = [_normalize_pokemon(p) for p in (opp.bench or [])] if opp else []
        opp_deck_count  = opp.deckCount if opp else 0
        energy_attached = bool(current.energyAttached)
        retreated       = bool(current.retreated)
        supporter_played= bool(current.supporterPlayed)
        turn            = int(current.turn or 0)

    return {
        'your_index':       your_index,
        'prizes_remaining': prizes_left,
        'prizes_taken':     6 - prizes_left,
        'hand_count':       me_hand_count,
        'hand':             me_hand_ids,
        'deck_count':       me_deck_count,
        'bench':            me_bench,
        'active_pokemon':   _normalize_pokemon(me_active_raw),
        'energy_attached':  energy_attached,
        'retreated':        retreated,
        'supporter_played': supporter_played,
        'turn':             turn,
        'opponent': {
            'prizes_remaining': opp_prizes_left,
            'active_pokemon':   _normalize_pokemon(opp_active_raw),
            'bench':            opp_bench,
            'deck_count':       opp_deck_count,
        },
    }


def _opt_to_dict(o) -> dict:
    """Convert a typed Option dataclass to a plain dict for policy scoring."""
    if isinstance(o, dict):
        return o
    return {
        "type":        int(o.type)                                       if o.type        is not None else None,
        "cardId":      getattr(o, 'cardId',      None),
        "attackId":    getattr(o, 'attackId',    None),
        "index":       getattr(o, 'index',       None),
        "area":        int(o.area)                                       if getattr(o, 'area', None)        is not None else None,
        "playerIndex": getattr(o, 'playerIndex', None),
        "inPlayArea":  int(o.inPlayArea)                                 if getattr(o, 'inPlayArea', None)  is not None else None,
        "inPlayIndex": getattr(o, 'inPlayIndex', None),
        "count":       getattr(o, 'count',       None),
        "number":      getattr(o, 'number',      None),
        "toolIndex":   getattr(o, 'toolIndex',   None),
        "energyIndex": getattr(o, 'energyIndex', None),
    }


# AreaType integer constants (mirrors cg/api.py AreaType enum)
_AREA_DECK    = 1
_AREA_HAND    = 2
_AREA_DISCARD = 3
_AREA_ACTIVE  = 4
_AREA_BENCH   = 5
_AREA_LOOKING = 12


def _resolve_card_id(o: dict, obs) -> tuple[str | None, str | None]:
    """
    Resolve the actual card ID and name from an option dict + live observation.

    PLAY options never carry cardId — only hand index.
    CARD/ATTACH/EVOLVE options reference cards by area+index.
    Returns (card_id_str, card_name) or (None, None).
    """
    try:
        opt_type = o.get("type")
        area     = o.get("area")
        idx      = o.get("index")
        p_raw    = o.get("playerIndex")

        current  = getattr(obs, "current", None)
        select   = getattr(obs, "select",  None)
        if current is None:
            return None, None

        players  = current.players or []
        your_idx = int(current.yourIndex or 0)
        p_idx    = int(p_raw) if p_raw is not None else your_idx
        player   = players[p_idx] if p_idx < len(players) else None
        hand     = (player.hand or []) if player else []

        card = None

        if opt_type == 7:           # PLAY: index = hand position
            if idx is not None and idx < len(hand):
                card = hand[idx]

        elif opt_type in (3, 4, 5): # CARD / TOOL_CARD / ENERGY_CARD
            if area == _AREA_HAND:
                if idx is not None and idx < len(hand):
                    card = hand[idx]
            elif area == _AREA_DECK:
                deck_cards = getattr(select, "deck", None) or []
                if idx is not None and idx < len(deck_cards):
                    card = deck_cards[idx]
            elif area == _AREA_LOOKING:
                looking = current.looking or []
                if idx is not None and idx < len(looking):
                    card = looking[idx]
            elif area == _AREA_BENCH:
                bench = (player.bench or []) if player else []
                if idx is not None and idx < len(bench):
                    poke = bench[idx]
                    if poke is not None:
                        if opt_type == 5:
                            ei = o.get("energyIndex")
                            if ei is not None:
                                ecs = poke.energyCards or []
                                if ei < len(ecs):
                                    card = ecs[ei]
                        elif opt_type == 4:
                            ti = o.get("toolIndex")
                            if ti is not None:
                                tl = poke.tools or []
                                if ti < len(tl):
                                    card = tl[ti]
                        elif opt_type == 3:
                            # SWITCH / TO_ACTIVE: option IS the bench Pokemon itself
                            poke_id = getattr(poke, 'id', None)
                            if poke_id is not None:
                                cdata = card_table.get(poke_id)
                                name  = getattr(cdata, 'name', '') if cdata else ''
                                return str(poke_id), name
            elif area == _AREA_ACTIVE:
                active_list = (player.active or []) if player else []
                poke = active_list[0] if active_list else None
                if poke is not None:
                    if opt_type == 5:
                        ei = o.get("energyIndex")
                        if ei is not None:
                            ecs = poke.energyCards or []
                            if ei < len(ecs):
                                card = ecs[ei]
                    elif opt_type == 4:
                        ti = o.get("toolIndex")
                        if ti is not None:
                            tl = poke.tools or []
                            if ti < len(tl):
                                card = tl[ti]
                    elif opt_type == 3:
                        # Pick the active Pokemon itself (rare but possible)
                        poke_id = getattr(poke, 'id', None)
                        if poke_id is not None:
                            cdata = card_table.get(poke_id)
                            name  = getattr(cdata, 'name', '') if cdata else ''
                            return str(poke_id), name

        elif opt_type == 10:    # ABILITY: area/index = the Pokémon using the ability
            if area == _AREA_ACTIVE:
                active_list = (player.active or []) if player else []
                poke = active_list[0] if active_list else None
                if poke is not None:
                    poke_id = getattr(poke, 'id', None)
                    if poke_id is not None:
                        cdata = card_table.get(poke_id)
                        name  = getattr(cdata, 'name', '') if cdata else ''
                        return str(poke_id), name
            elif area == _AREA_BENCH:
                bench = (player.bench or []) if player else []
                poke  = bench[idx] if idx is not None and idx < len(bench) else None
                if poke is not None:
                    poke_id = getattr(poke, 'id', None)
                    if poke_id is not None:
                        cdata = card_table.get(poke_id)
                        name  = getattr(cdata, 'name', '') if cdata else ''
                        return str(poke_id), name

        elif opt_type in (8, 9):    # ATTACH / EVOLVE: area/index = card to attach/evolve
            if area == _AREA_HAND:
                if idx is not None and idx < len(hand):
                    card = hand[idx]

        if card is not None:
            cid   = str(card.id)
            cdata = card_table.get(card.id)
            name  = getattr(cdata, "name", "") if cdata else ""
            return cid, name

        # Fallback: explicit cardId field (ATTACK has attackId not cardId; skip)
        direct_cid = o.get("cardId")
        if direct_cid is not None:
            cid_str = str(direct_cid)
            cdata   = card_table.get(int(direct_cid))
            name    = getattr(cdata, "name", "") if cdata else ""
            return cid_str, name

    except Exception:
        pass
    return None, None


def _enrich_options(
    opt_dicts: list,
    obs,
    select_context: int,
    remain_damage_counter: int = 0,
) -> None:
    """
    Mutate each option dict in-place to add resolved_card_id,
    resolved_card_name, select_context, and remain_damage_counter.
    """
    for o in opt_dicts:
        o["select_context"]        = select_context
        o["remain_damage_counter"] = remain_damage_counter
        cid, name = _resolve_card_id(o, obs)
        o["resolved_card_id"]   = cid
        o["resolved_card_name"] = name


def _extract_opp_events(obs_logs, opp_idx: int) -> list:
    """
    Parse cabt Log events and return (cardId, event_type) pairs for the opponent.
    LogType integers: PLAY=10, EVOLVE=12, ATTACK=15
    Returns [] on any error — never raises.
    """
    result = []
    try:
        for log in (obs_logs or []):
            if getattr(log, 'playerIndex', None) != opp_idx:
                continue
            lt  = int(getattr(log, 'type', -1))
            cid = getattr(log, 'cardId', None)
            if lt == 10 and cid is not None:    # PLAY
                result.append((int(cid), "play"))
            elif lt == 15 and cid is not None:  # ATTACK
                result.append((int(cid), "attack"))
            elif lt == 12 and cid is not None:  # EVOLVE (cardId = evolved form)
                result.append((int(cid), "evolve"))
    except Exception:
        pass
    return result


def _build_opp_card_list(opp_seen: dict) -> list:
    """Convert _opp_seen dict to a JSON-serialisable list for log_result()."""
    entries = []
    try:
        for cid, evts in sorted(opp_seen.items()):
            cdata = card_table.get(cid)
            name  = getattr(cdata, 'name', '') if cdata is not None else ''
            entries.append({
                "card_id": cid,
                "name":    name,
                "events":  sorted(evts),
            })
    except Exception:
        pass
    return entries


def _build_adv_info(state: dict, opt_dicts: list, selected: list) -> dict | None:
    """Build advantage breakdown for the selected action (for logging)."""
    try:
        if not _policy or not selected or not opt_dicts:
            return None
        from agent.advantage import breakdown
        from agent.win_condition import (
            detect_current_phase, evaluate_plan_progress, get_missing_plan_pieces
        )
        idx    = selected[0] if selected else 0
        action = opt_dicts[idx] if idx < len(opt_dicts) else {}
        phase  = detect_current_phase(state)
        dp     = getattr(_policy, "deck_profile", {})
        adv    = breakdown(action, state, _policy.knowledge, phase, dp)
        adv["phase"]          = phase
        adv["archetype"]      = dp.get("archetype", "unknown")
        adv["plan_progress"]  = round(evaluate_plan_progress(state, dp, _policy.knowledge), 3)
        adv["missing_pieces"] = get_missing_plan_pieces(state, dp, _policy.knowledge)
        return adv
    except Exception:
        return None


# Score threshold per SelectContext for optional selections (min_count=0).
# If the best available option scores below this, we return [] — i.e. we choose
# not to act at all rather than making a low-value pick.
# Keys are SelectContext integer values from cg/api.py.
_OPT_THRESHOLD: dict = {
    5:  5.0,   # TO_BENCH              — bench only high-value Pokémon
    7:  4.0,   # TO_HAND               — take only useful cards
    8:  5.0,   # DISCARD               — only discard genuinely disposable cards
    9:  4.0,   # TO_DECK               — return to deck only if worthwhile
    10: 4.0,   # TO_DECK_BOTTOM
    13: 10.0,  # DAMAGE_COUNTER        — place counters only on meaningful targets
    14: 10.0,  # DAMAGE_COUNTER_ANY
    15: 10.0,  # DAMAGE
    16: 4.0,   # REMOVE_DAMAGE_COUNTER — heal if noticeably damaged
    17: 3.0,   # HEAL                  — heal even minor damage
}
_OPT_THRESHOLD_DEFAULT = 3.0


def _select_indices(
    state: dict,
    opt_dicts: list,
    max_count: int,
    min_count: int = 0,
    obs=None,
) -> list:
    """
    Return a list of indices into options, scored by policy + lookahead.

    1. PolicyAgent._score() provides immediate scores for every action.
    2. When min_count=0, options below _OPT_THRESHOLD are excluded; if none
       survive the threshold the function returns [] (skip optional selection).
    3. Planner.select() uses immediate scores plus 1-ply rollout.
    4. Falls back to greedy immediate-score ranking on any error.
    """
    n = len(opt_dicts)

    # Only skip scoring when ALL options must be chosen (no real decision).
    if min_count == max_count == n:
        return list(range(n))

    # --- immediate scores (always computed) ---
    immediate_scores: list[float] = []
    if _policy:
        try:
            immediate_scores = [
                _policy._score(opt, state)[0] if isinstance(opt, dict) else 0.0
                for opt in opt_dicts
            ]
        except Exception:
            immediate_scores = [0.0] * n
    else:
        immediate_scores = [0.0] * n

    # --- terminal-action suppression ---
    # Attack ends the turn. If the plan requires a pre-attack action (Boss's
    # Orders, switch, energy attach) AND that action is available in the current
    # legal options, reduce all Attack scores so PRE_ATTACK actions win.
    if _policy is not None:
        try:
            immediate_scores = _policy.suppress_attack_if_pre_required(
                state, opt_dicts, immediate_scores
            )
        except Exception:
            pass

    # --- optional-selection threshold (min_count=0 = agent may choose nothing) ---
    # If the best option scores below the context threshold, return [] explicitly
    # rather than forcing a low-value pick.  Options below threshold are nulled
    # (-999) so planner/greedy never selects them.
    _opt_thresh_active = False
    if min_count == 0 and n > 0:
        ctx    = opt_dicts[0].get("select_context", -1) if opt_dicts else -1
        thresh = _OPT_THRESHOLD.get(ctx, _OPT_THRESHOLD_DEFAULT)
        best   = max(immediate_scores) if immediate_scores else -999.0
        if best < thresh:
            return []   # all options below threshold — skip optional selection
        immediate_scores = [s if s >= thresh else -999.0 for s in immediate_scores]
        _opt_thresh_active = True

    # --- planner with lookahead ---
    if _planner is not None:
        try:
            result = _planner.select(
                state=state,
                opt_dicts=opt_dicts,
                immediate_scores=immediate_scores,
                max_count=max_count,
                min_count=min_count,
                obs=obs,
                known_deck=_DECK,
                card_table=card_table,
                board_to_state=_board_to_state,
            )
            if _opt_thresh_active:
                result = [i for i in result if i < n and immediate_scores[i] > -900.0]
            return result
        except Exception:
            pass

    # --- Iono's Poffin / ToBench diversity guard (ctx in (2,5), max_count>1) ---
    # Prevents picking two copies of the same basic (Voltorb+Voltorb etc.).
    # Spread Tadbulb / Voltorb / Wattrel first; allow duplicates only to meet min_count.
    try:
        if n > 0 and max_count > 1:
            _ctx0 = opt_dicts[0].get("select_context", -1) if opt_dicts else -1
            if _ctx0 in (2, 5):
                _IONO_BASICS = {"265", "268", "270"}
                ranked = sorted(enumerate(immediate_scores), key=lambda x: -x[1])
                selected_diverse: list = []
                seen_cids: set = set()
                for i, s in ranked:
                    if s <= -900.0:
                        continue
                    _cid = str(opt_dicts[i].get("resolved_card_id", ""))
                    if _cid in _IONO_BASICS and _cid in seen_cids:
                        continue
                    selected_diverse.append(i)
                    if _cid in _IONO_BASICS:
                        seen_cids.add(_cid)
                    if len(selected_diverse) >= max_count:
                        break
                # Backfill duplicates if min_count not yet met
                if len(selected_diverse) < max(min_count, 1):
                    for i, s in ranked:
                        if i in selected_diverse or s <= -900.0:
                            continue
                        selected_diverse.append(i)
                        if len(selected_diverse) >= max_count:
                            break
                if len(selected_diverse) >= min_count:
                    return selected_diverse[:max_count]
    except Exception:
        pass

    # --- greedy fallback ---
    scored = sorted(enumerate(immediate_scores), key=lambda x: -x[1])
    if _opt_thresh_active:
        result = [i for i, s in scored if s > -900.0][:max_count]
    else:
        result = [i for i, _ in scored[:max_count]]
        if len(result) < min_count:
            extra = [i for i in range(n) if i not in result]
            result += extra[: min_count - len(result)]
    return result


# ──────────────────────────────────────────────────────────────
# Kaggle agent entry point
# ──────────────────────────────────────────────────────────────

def agent(obs_dict, config=None):
    """
    Called every turn by the kaggle-environments harness.
    Returns list[int]: indices of selected options.
    """
    global _policy, _logger, _opp_seen, _last_game_turn
    if _policy is None:
        _init()

    obs = to_observation_class(obs_dict)

    if obs.select is None:
        return _DECK

    select    = obs.select
    options   = select.option or []
    max_count = int(select.maxCount or 1)
    min_count = int(select.minCount or 0)

    if not options:
        return []

    # ── Opponent tracking ─────────────────────────────────────────
    current_turn = 0
    opp_idx      = 1
    game_over    = False
    try:
        if obs.current is not None:
            current_turn = int(obs.current.turn or 0)
            opp_idx      = 1 - int(obs.current.yourIndex or 0)
            game_over    = (obs.current.result != -1)
            # Detect new game: turn resets while we tracked a later turn
            if current_turn <= 1 and _last_game_turn > 3:
                _opp_seen = {}
            _last_game_turn = current_turn
    except Exception:
        pass

    try:
        for cid, evt in _extract_opp_events(obs.logs, opp_idx):
            if cid not in _opp_seen:
                _opp_seen[cid] = set()
            _opp_seen[cid].add(evt)
    except Exception:
        pass

    # ── Action selection ──────────────────────────────────────────
    state      = _board_to_state(obs.current)
    opt_dicts  = [_opt_to_dict(o) for o in options]
    select_ctx = int(getattr(select, "context", 0) or 0)
    select_typ = int(getattr(select, "type",    0) or 0)

    # Enrich every option with resolved card ID + context
    remain_dc = int(getattr(select, "remainDamageCounter", 0) or 0)
    _enrich_options(opt_dicts, obs, select_ctx, remain_dc)

    if _policy and _compute_plan is not None:
        try:
            _policy.current_plan = _compute_plan(
                obs, card_table, getattr(_policy, '_attack_full', {})
            )
        except Exception:
            _policy.current_plan = None

    # --- Score breakdown for all candidates ---
    # Cache opt_dicts on the policy so _score_with_breakdown() can access all
    # options when computing turn_rule_engine scores (needs full select context).
    if _policy:
        _policy._current_opt_dicts = opt_dicts

    # _score_with_breakdown() returns (total, reason, {type_score, adv_score,
    # rule_bonus, rule_reason, turn_rule_score, turn_rule_reason})
    _cand_bd: list = []
    if _policy:
        try:
            _cand_bd = [_policy._score_with_breakdown(o, state) for o in opt_dicts]
        except Exception:
            _cand_bd = [(0.0, "score_error", {})] * len(opt_dicts)
    else:
        _cand_bd = [(0.0, "no_policy", {})] * len(opt_dicts)

    # --- Turn-rule debug records (option_class, is_attack, etc.) for logging ---
    _tr_debug: list = []
    try:
        from agent.turn_rule_engine import option_debug_record
        _tr_synthetic = {"option": opt_dicts}
        _tr_debug = [option_debug_record(o, state, _tr_synthetic) for o in opt_dicts]
    except Exception:
        _tr_debug = [{}] * len(opt_dicts)

    candidate_scores = [(s, r) for s, r, _ in _cand_bd]
    _breakdowns      = [bd     for _, _, bd in _cand_bd]

    # Pre/post-suppression comparison — used to compute attack_suppression field
    _pre_sup = [s for s, _ in candidate_scores]
    _post_sup = list(_pre_sup)
    if _policy:
        try:
            _post_sup = _policy.suppress_attack_if_pre_required(state, opt_dicts, _post_sup)
        except Exception:
            pass
    _sup_pen = [
        round(a - b, 3) if abs(a - b) > 0.01 else 0.0
        for a, b in zip(_pre_sup, _post_sup)
    ]

    # --- Run selection ---
    t0 = time.time()
    planner_used = False
    try:
        result = _select_indices(state, opt_dicts, max_count, min_count, obs)
        planner_used = (_planner is not None)
    except Exception:
        count  = max(min_count, min(1, len(options)))
        result = list(range(count))
    elapsed_ms = int((time.time() - t0) * 1000)

    # Planner last-run details (set inside _select_indices by Planner.select())
    _pf = getattr(_planner, "last_final_scores",  {}) if _planner else {}
    _pfu= getattr(_planner, "last_future_scores", {}) if _planner else {}
    _pt = getattr(_planner, "last_threat_scores", {}) if _planner else {}
    rollout_success = getattr(_planner, "last_rollout_used", False) if _planner else False

    sel_idx    = result[0] if result else 0
    # Use planner final score when available, else post-suppression immediate score
    sel_score  = round(_pf.get(sel_idx, _post_sup[sel_idx] if sel_idx < len(_post_sup) else 0.0), 4) if candidate_scores else 0.0
    sel_reason = candidate_scores[sel_idx][1] if candidate_scores else "unknown"
    sel_cid    = opt_dicts[sel_idx].get("resolved_card_id")   if opt_dicts else None
    sel_cname  = opt_dicts[sel_idx].get("resolved_card_name") if opt_dicts else None
    sel_number = opt_dicts[sel_idx].get("number") if (opt_dicts and select_typ == 8) else None

    # Optional-selection skip: when min_count=0 and we returned [] consciously
    optional_skip_reason = None
    if not result and min_count == 0:
        ctx    = opt_dicts[0].get("select_context", -1) if opt_dicts else -1
        thresh = _OPT_THRESHOLD.get(ctx, _OPT_THRESHOLD_DEFAULT)
        optional_skip_reason = f"optional_skip_ctx{ctx}_thresh{thresh}"
        sel_reason = optional_skip_reason

    # --- Plan info (once per turn) ---
    _plan = getattr(_policy, "current_plan", None) if _policy else None
    plan_log = {}
    if _plan is not None and _plan.has_plan:
        _opp_active_cid = str(state.get("opponent", {}).get("active_pokemon", {}).get("card_id", ""))
        _target_cid     = str(_plan.target_card_id or "")
        plan_log = {
            "goal":                    _plan.goal,
            "need_boss":               _plan.need_boss,
            "need_energy":             _plan.need_energy,
            "need_switch":             _plan.need_switch,
            "target_card_id":          _plan.target_card_id,
            "target_zone":             _plan.target_zone,
            "target_active":           _plan.target_active,
            "pre_attack_requirements": _plan.pre_attack_requirements,
            "ko_expected":             _plan.ko_expected,
            "attack_target_matches":   (_target_cid == _opp_active_cid) if _target_cid else None,
        }

    candidates = [
        {
            "option_index":       i,
            "option_type":        o.get("type"),
            "select_context":     select_ctx,
            "resolved_card_id":   o.get("resolved_card_id"),
            "resolved_card_name": o.get("resolved_card_name"),
            # Raw option fields for diagnostics
            "cardId":             o.get("cardId"),
            "attackId":           o.get("attackId"),
            "area":               o.get("area"),
            "index":              o.get("index"),
            "playerIndex":        o.get("playerIndex"),
            "inPlayArea":         o.get("inPlayArea"),
            "inPlayIndex":        o.get("inPlayIndex"),
            # Score breakdown
            "raw_score":          round(_pre_sup[i], 3) if i < len(_pre_sup) else 0.0,
            "type_score":         _breakdowns[i].get("type_score",      0.0) if i < len(_breakdowns) else 0.0,
            "rule_bonus":         _breakdowns[i].get("rule_bonus",       0.0) if i < len(_breakdowns) else 0.0,
            "rule_reason":        _breakdowns[i].get("rule_reason",      "")  if i < len(_breakdowns) else "",
            "turn_rule_score":    _breakdowns[i].get("turn_rule_score",  0.0) if i < len(_breakdowns) else 0.0,
            "turn_rule_reason":   _breakdowns[i].get("turn_rule_reason", "")  if i < len(_breakdowns) else "",
            "kilowattrel_ability_score":  _breakdowns[i].get("kilowattrel_ability_score",  0.0) if i < len(_breakdowns) else 0.0,
            "kilowattrel_ability_reason": _breakdowns[i].get("kilowattrel_ability_reason", "")  if i < len(_breakdowns) else "",
            "voltorb_attack_score":      _breakdowns[i].get("voltorb_attack_score",      0.0) if i < len(_breakdowns) else 0.0,
            "voltorb_attack_reason":     _breakdowns[i].get("voltorb_attack_reason",     "")  if i < len(_breakdowns) else "",
            "voltorb_safety_score":      _breakdowns[i].get("voltorb_safety_score",      0.0) if i < len(_breakdowns) else 0.0,
            "voltorb_safety_reason":     _breakdowns[i].get("voltorb_safety_reason",     "")  if i < len(_breakdowns) else "",
            "attack_suppression": _sup_pen[i] if i < len(_sup_pen) else 0.0,
            "final_score":        round(_pf.get(i, _post_sup[i]), 3) if i < len(_post_sup) else 0.0,
            "future_score":       round(_pfu.get(i, 0.0), 3),
            "threat_score":       round(_pt.get(i, 0.0), 3),
            # Turn-rule classification
            "option_class":            _tr_debug[i].get("option_class",            "") if i < len(_tr_debug) else "",
            "is_attack":               _tr_debug[i].get("is_attack",               False) if i < len(_tr_debug) else False,
            "is_ability":              _tr_debug[i].get("is_ability",              False) if i < len(_tr_debug) else False,
            "is_retreat":              _tr_debug[i].get("is_retreat",              False) if i < len(_tr_debug) else False,
            "is_end":                  _tr_debug[i].get("is_end",                  False) if i < len(_tr_debug) else False,
            "is_turn_ending":          _tr_debug[i].get("is_turn_ending",          False) if i < len(_tr_debug) else False,
            "can_continue_after":      _tr_debug[i].get("can_continue_after",      True)  if i < len(_tr_debug) else True,
            "has_legal_attack_option": _tr_debug[i].get("has_legal_attack_option", False) if i < len(_tr_debug) else False,
            # Selection indicator
            "selected":           i in result,
            "reason":             candidate_scores[i][1] if i < len(candidate_scores) else "",
        }
        for i, o in enumerate(opt_dicts)
    ]

    adv_info = _build_adv_info(state, opt_dicts, result)
    iono_log = None
    if _build_ionos_log is not None:
        try:
            sel_opt = opt_dicts[sel_idx] if sel_idx < len(opt_dicts) else {}
            iono_log = _build_ionos_log(state, sel_opt)
        except Exception:
            pass
    if _logger:
        _logger.log(
            state=state,
            legal_actions=opt_dicts,
            selected_action=result,
            selected_score=sel_score,
            reason=sel_reason,
            error=None,
            time_ms=elapsed_ms,
            adv_info=adv_info,
            select_type=select_typ,
            select_context=select_ctx,
            resolved_card_id=sel_cid,
            resolved_card_name=sel_cname,
            planner_used=planner_used,
            rollout_success=rollout_success,
            candidates=candidates,
            selected_number=sel_number,
            optional_skip_reason=optional_skip_reason,
            plan_log=plan_log,
            deck_log=iono_log,
        )

    # ── Game-end summary ─────────────────────────────────────────
    if game_over and _logger:
        try:
            won        = (obs.current.result == int(obs.current.yourIndex or 0))
            result_str = "win" if won else "loss"
            _logger.log_result(
                result=result_str,
                total_turns=current_turn,
                opp_cards_seen=_build_opp_card_list(_opp_seen),
            )
        except Exception:
            pass

    return result
