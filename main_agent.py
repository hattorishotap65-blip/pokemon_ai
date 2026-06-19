"""
Competition entry point — cabt (Card AI Battle) engine on kaggle-environments.

API spec: https://matsuoinstitute.github.io/cabt/

Each turn the harness calls:
    action = agent(obs, config)

obs fields:
    obs["step"]               -- current step number
    obs["current"]            -- State dict or None during deck phase
    obs["select"]             -- SelectData dict or None
    obs["logs"]               -- list of past event dicts
    obs["remainingOverageTime"]

Return value: list[int]  -- indices into obs["select"]["option"]
    []     = nothing to select / pass
    [0]    = pick the first option
    [i, j] = pick options i and j (when maxCount > 1)

State dict (obs["current"]):
    turn, yourIndex, firstPlayer, supporterPlayed, energyAttached, retreated,
    players: list[PlayerState]

PlayerState dict (obs["current"]["players"][n]):
    active: list[Pokemon|None]    handCount, deckCount, benchMax
    bench: list[Pokemon]          prize: list[Card|None]
    hand: list[Card]|None         discard: list[Card]
    poisoned, burned, asleep, paralyzed, confused: bool

Pokemon dict:
    id, serial, hp, maxHp, appearThisTurn, energies, energyCards, tools, preEvolution

SelectData dict (obs["select"]):
    type, context, minCount, maxCount, option: list[Option]

Option dict:
    type (OptionType int), cardId, attackId, index, area, playerIndex, count, ...
"""
import sys
import os
import time

try:
    _agent_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _agent_dir = '/kaggle_simulations/agent'
sys.path.insert(0, _agent_dir)

from agent.policy import PolicyAgent
from agent.logger import GameLogger

# Load deck once at startup — returned to cabt when obs["select"] is None
try:
    with open(os.path.join(_agent_dir, 'deck.csv')) as _f:
        _DECK = [int(l.strip()) for l in _f if l.strip()]
except Exception:
    _DECK = []

_policy: PolicyAgent = None
_logger: GameLogger = None
AGENT_VERSION = "v2"
DECK_NAME = "raging_bolt_ex"


def _init():
    global _policy, _logger
    _policy = PolicyAgent()
    _logger = GameLogger(deck_name=DECK_NAME, agent_version=AGENT_VERSION)


# ──────────────────────────────────────────────────────────────
# Observation helpers
# ──────────────────────────────────────────────────────────────

def _field(obs, key):
    """Read a field from obs whether it's a dict or a namespace object."""
    if isinstance(obs, dict):
        return obs.get(key)
    return getattr(obs, key, None)


def _normalize_pokemon(p) -> dict:
    """
    Convert a cabt Pokemon dict (camelCase) to our internal snake_case format
    so that policy.py and evaluator.py can use consistent field names.
    """
    if not isinstance(p, dict):
        return {}
    return {
        "card_id":      str(p.get("id", "")),
        "hp_remaining": p.get("hp", 0),
        "max_hp":       p.get("maxHp", 1) or 1,
        "energy_count": len(p.get("energies") or []),
        "energies":     p.get("energies") or [],
    }


def _board_to_state(current) -> dict:
    """
    Convert obs["current"] (State dict) to the internal state format that
    policy.py / evaluator.py expect.

    Uses yourIndex so we correctly identify our player vs opponent even when
    we are player 1.
    """
    if not isinstance(current, dict):
        return {}

    players = current.get('players') or []
    your_index = int(current.get('yourIndex') or 0)
    opp_index  = 1 - your_index

    me  = players[your_index] if your_index < len(players) and isinstance(players[your_index], dict) else {}
    opp = players[opp_index]  if opp_index  < len(players) and isinstance(players[opp_index],  dict) else {}

    me_active_raw  = next(iter(me.get('active')  or []), None)
    opp_active_raw = next(iter(opp.get('active') or []), None)

    prizes_left     = sum(1 for p in (me.get('prize')  or []) if p is None)
    opp_prizes_left = sum(1 for p in (opp.get('prize') or []) if p is None)

    return {
        'prizes_remaining': prizes_left,
        'prizes_taken':     6 - prizes_left,
        'hand_count':       me.get('handCount', 0),
        'deck_count':       me.get('deckCount', 0),
        'bench':            [_normalize_pokemon(p) for p in (me.get('bench') or [])],
        'active_pokemon':   _normalize_pokemon(me_active_raw),
        # Turn-state flags from State (prevent illegal double-actions)
        'energy_attached':  bool(current.get('energyAttached')),
        'retreated':        bool(current.get('retreated')),
        'supporter_played': bool(current.get('supporterPlayed')),
        'turn':             int(current.get('turn') or 0),
        'opponent': {
            'prizes_remaining': opp_prizes_left,
            'active_pokemon':   _normalize_pokemon(opp_active_raw),
            'bench':            [_normalize_pokemon(p) for p in (opp.get('bench') or [])],
            'deck_count':       opp.get('deckCount', 0),
        },
    }


def _select_indices(state: dict, options: list, max_count: int, min_count: int = 0) -> list:
    """
    Return a list of indices into options.

    Respects both maxCount (upper bound) and minCount (lower bound).
    Falls back to first N indices if policy scoring fails.
    """
    n = len(options)

    # Must take all if maxCount >= total options
    if max_count >= n:
        return list(range(n))

    # Policy scoring
    try:
        if _policy:
            scored = []
            for i, opt in enumerate(options):
                score = _policy._score(opt, state)[0] if isinstance(opt, dict) else 0.0
                scored.append((score, i))
            scored.sort(reverse=True)
            result = [idx for _, idx in scored[:max_count]]
            # Enforce minCount
            if len(result) < min_count:
                extra = [i for i in range(n) if i not in result]
                result += extra[:min_count - len(result)]
            return result
    except Exception:
        pass

    # Safe fallback: satisfy minCount <= count <= maxCount
    count = max(min_count, min(max_count, n))
    return list(range(count))


# ──────────────────────────────────────────────────────────────
# Kaggle agent entry point
# ──────────────────────────────────────────────────────────────

def agent(obs, config=None):
    """
    Called every turn by the kaggle-environments harness.
    Returns list[int]: indices of selected options.
    """
    global _policy, _logger
    if _policy is None:
        _init()

    select = _field(obs, 'select')

    # Step 0: select is None → cabt expects the deck (60 card IDs)
    if select is None:
        return _DECK

    if not isinstance(select, dict):
        return _DECK

    options   = select.get('option') or []
    max_count = int(select.get('maxCount') or 1)
    min_count = int(select.get('minCount') or 0)

    if not options:
        return []

    current = _field(obs, 'current')
    state   = _board_to_state(current)

    t0 = time.time()
    try:
        result = _select_indices(state, options, max_count, min_count)
    except Exception:
        count  = max(min_count, min(1, len(options)))
        result = list(range(count))
    elapsed_ms = int((time.time() - t0) * 1000)

    if _logger:
        _logger.log(
            state=state,
            legal_actions=options,
            selected_action=result,
            selected_score=0.0,
            reason="index_select",
            error=None,
            time_ms=elapsed_ms,
        )

    return result
