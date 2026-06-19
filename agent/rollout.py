"""
One-ply lookahead via cg.api search_begin / search_step.

Public API
----------
is_available() -> bool
evaluate_candidates(obs, known_deck, candidate_indices, card_table, deadline)
    -> dict[int, Observation]   # action_idx -> future Observation (may be partial)

Hidden card estimation strategy
--------------------------------
- Our deck/prizes  : derived from known_deck minus visible zones
- Opponent deck    : use our deck as structural placeholder (counts must match)
- Opponent prizes  : same placeholder logic
- Opponent hand    : same placeholder logic
- Opp face-down active : first Basic Pokemon from our deck

If search_begin_input is None (local/test env) or libcg.so fails to load,
is_available() returns False and evaluate_candidates returns {} immediately.
"""

import random
import time
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cg.api import Observation

# ---------------------------------------------------------------------------
# Lazy availability check — cg.api loads libcg.so at import time
# ---------------------------------------------------------------------------

_SEARCH_AVAILABLE: bool | None = None   # None = not yet checked


def is_available() -> bool:
    global _SEARCH_AVAILABLE
    if _SEARCH_AVAILABLE is None:
        try:
            from cg.api import search_begin, search_step, search_end, search_release  # noqa: F401
            _SEARCH_AVAILABLE = True
        except Exception:
            _SEARCH_AVAILABLE = False
    return _SEARCH_AVAILABLE


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate_candidates(
    obs: "Observation",
    known_deck: list[int],
    candidate_indices: list[int],
    card_table: dict,
    deadline: float,
) -> "dict[int, Observation]":
    """
    For each index in candidate_indices, apply that action from obs and
    return the resulting Observation.

    A single search_begin call is made; each candidate branches from the
    same root via search_step, so the C engine is initialised only once.

    Returns {} on any initialisation failure or if deadline is already past.
    """
    if not is_available():
        return {}
    if not candidate_indices:
        return {}
    if time.time() >= deadline:
        return {}
    if obs is None or obs.current is None:
        return {}

    results: dict[int, "Observation"] = {}

    try:
        from cg.api import search_begin, search_step, search_end, search_release

        est = _estimate_hidden(obs, known_deck, card_table)

        root = search_begin(
            obs,
            your_deck=est["your_deck"],
            your_prize=est["your_prize"],
            opponent_deck=est["opp_deck"],
            opponent_prize=est["opp_prize"],
            opponent_hand=est["opp_hand"],
            opponent_active=est["opp_active"],
        )
        root_id = root.searchId

        for idx in candidate_indices:
            if time.time() >= deadline:
                break
            try:
                next_state = search_step(root_id, [idx])
                results[idx] = next_state.observation
                # Release the branch node; root is kept for other candidates
                search_release(next_state.searchId)
            except Exception:
                pass    # invalid move or engine error — skip this candidate

        search_end()

    except Exception:
        # search_begin failed (no search_begin_input, bad estimates, etc.)
        try:
            from cg.api import search_end as se
            se()
        except Exception:
            pass

    return results


# ---------------------------------------------------------------------------
# Hidden card estimation
# ---------------------------------------------------------------------------

def _estimate_hidden(obs: "Observation", known_deck: list[int], card_table: dict) -> dict:
    """
    Build estimated card lists for search_begin.

    Lengths must satisfy:
      len(your_deck)  >= state.players[us].deckCount
      len(your_prize) >= len(state.players[us].prize)
      len(opp_deck)   >= state.players[opp].deckCount
      len(opp_prize)  >= len(state.players[opp].prize)
      len(opp_hand)   >= state.players[opp].handCount
    """
    state = obs.current
    our_idx = state.yourIndex
    opp_idx = 1 - our_idx
    me  = state.players[our_idx]
    opp = state.players[opp_idx]

    # ---- OUR HIDDEN CARDS ----
    pool = Counter(known_deck)

    def _subtract(cid: int) -> None:
        if pool[cid] > 0:
            pool[cid] -= 1

    for card in (me.hand or []):
        _subtract(card.id)

    def _subtract_pokemon(p) -> None:
        if p is None:
            return
        _subtract(p.id)
        for c in (p.preEvolution or []):
            _subtract(c.id)
        for c in (p.energyCards or []):
            _subtract(c.id)
        for c in (p.tools or []):
            _subtract(c.id)

    for p in (me.active or []):
        _subtract_pokemon(p)
    for p in (me.bench or []):
        _subtract_pokemon(p)
    for c in (me.discard or []):
        _subtract(c.id)

    remaining = [cid for cid, cnt in pool.items() for _ in range(max(0, cnt))]
    random.shuffle(remaining)

    n_prize = len(me.prize)
    n_deck  = me.deckCount

    # Pad if card accounting leaves us short
    while len(remaining) < n_deck + n_prize:
        remaining += known_deck[:max(1, n_deck + n_prize - len(remaining))]

    your_deck_est  = remaining[:n_deck]
    your_prize_est = remaining[n_deck:n_deck + n_prize]

    # ---- OPPONENT HIDDEN CARDS ----
    # Use our deck as a structurally valid placeholder for unknown opp cards.
    n_opp_deck  = opp.deckCount
    n_opp_prize = len(opp.prize)
    n_opp_hand  = opp.handCount
    total_opp   = n_opp_deck + n_opp_prize + n_opp_hand + 1

    filler = list(known_deck) * (total_opp // max(1, len(known_deck)) + 2)
    opp_deck_est  = filler[:n_opp_deck]
    opp_prize_est = filler[:n_opp_prize]
    opp_hand_est  = filler[:n_opp_hand]

    # Opponent face-down active Pokemon
    opp_active_est: list[int] = []
    if opp.active and opp.active[0] is None:
        basic_id = _find_basic(known_deck, card_table)
        opp_active_est = [basic_id] if basic_id is not None else known_deck[:1]

    return {
        "your_deck":  your_deck_est,
        "your_prize": your_prize_est,
        "opp_deck":   opp_deck_est,
        "opp_prize":  opp_prize_est,
        "opp_hand":   opp_hand_est,
        "opp_active": opp_active_est,
    }


def _find_basic(deck: list[int], card_table: dict) -> "int | None":
    """Return the first Basic Pokemon card ID found in deck."""
    for cid in deck:
        c = card_table.get(cid)
        if c is not None and getattr(c, "basic", False):
            return cid
    return None
