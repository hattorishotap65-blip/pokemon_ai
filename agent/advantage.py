"""
Per-action advantage evaluation.

Each evaluate_*_advantage() function returns a float derived from
card_knowledge adv fields. evaluate_total_advantage() applies
archetype x phase weights from deck_profile and concept_weights.

Scale: raw adv fields are 0-9. The total is divided by SCALE so the
final contribution to policy score stays in a comparable range (~0-10).
"""

from agent.concept_weights import get_weights

# OptionType integers (no import from policy to avoid circular deps)
_OT_ATTACK  = 13
_OT_END     = 14
_OT_RETREAT = 12

SCALE = 8.0  # divisor to bring sum into ~0-10 range

_ADV_KEYS = (
    "card_adv", "board_adv", "energy_adv", "tempo_adv",
    "prize_adv", "resource_adv", "info_adv", "risk_reduction_adv",
)


# ---------------------------------------------------------------------------
# Card ID resolution (mirrors policy._cid_from_hand without importing it)
# ---------------------------------------------------------------------------

def _resolve_cid(action: dict, state: dict) -> str:
    """Return the card_id most relevant to the action."""
    t = action.get("type")
    if t == _OT_ATTACK:
        return str(state.get("active_pokemon", {}).get("card_id", ""))
    if t == _OT_END:
        return ""
    if t == _OT_RETREAT:
        return str(state.get("active_pokemon", {}).get("card_id", ""))
    cid = str(action.get("cardId") or "")
    if cid:
        return cid
    idx = action.get("index")
    if idx is not None:
        hand = state.get("hand") or []
        if idx < len(hand):
            return str(hand[idx])
    return ""


def _adv(knowledge, cid: str, key: str, default: int = 3) -> int:
    return int(knowledge.get_score(cid, key, default))


# ---------------------------------------------------------------------------
# Individual advantage evaluators
# ---------------------------------------------------------------------------

def evaluate_card_advantage(action: dict, state: dict, knowledge) -> float:
    """Card/draw/search advantage: increases usable options."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    return float(_adv(knowledge, cid, "card_adv", 2))


def evaluate_board_advantage(action: dict, state: dict, knowledge) -> float:
    """Board advantage: strengthens our field position."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    return float(_adv(knowledge, cid, "board_adv", 3))


def evaluate_energy_advantage(action: dict, state: dict, knowledge) -> float:
    """Energy advantage: enables or accelerates attacks."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    return float(_adv(knowledge, cid, "energy_adv", 2))


def evaluate_tempo_advantage(action: dict, state: dict, knowledge) -> float:
    """Tempo advantage: act faster or slow the opponent."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    base = float(_adv(knowledge, cid, "tempo_adv", 3))
    # Attacking is inherently high-tempo
    if action.get("type") == _OT_ATTACK:
        base = max(base, 7.0)
    return base


def evaluate_prize_advantage(action: dict, state: dict, knowledge) -> float:
    """Prize advantage: progress toward winning the prize race."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    base = float(_adv(knowledge, cid, "prize_adv", 3))
    if action.get("type") == _OT_ATTACK:
        opp_hp = state.get("opponent", {}).get("active_pokemon", {}).get("hp_remaining", 9999)
        # Bonus when close to KO
        if opp_hp <= 60:
            base = max(base, 7.0)
    return base


def evaluate_resource_advantage(action: dict, state: dict, knowledge) -> float:
    """Resource advantage: preserve or recover key resources."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    return float(_adv(knowledge, cid, "resource_adv", 3))


def evaluate_info_advantage(action: dict, state: dict, knowledge) -> float:
    """Information advantage: learn about opponent's deck/hand."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    return float(_adv(knowledge, cid, "info_adv", 2))


def evaluate_risk_reduction(action: dict, state: dict, knowledge) -> float:
    """Risk reduction: lower the chance of losing through bad outcomes."""
    cid = _resolve_cid(action, state)
    if not cid:
        return 0.0
    base = float(_adv(knowledge, cid, "risk_reduction_adv", 3))
    # Extra bonus when our active is in danger
    active = state.get("active_pokemon", {})
    hp     = active.get("hp_remaining", 9999)
    max_hp = max(active.get("max_hp", 1) or 1, 1)
    if hp / max_hp <= 0.25:
        base += 2.0
    return base


# ---------------------------------------------------------------------------
# Combined evaluator
# ---------------------------------------------------------------------------

def evaluate_total_advantage(
    action: dict,
    state:  dict,
    knowledge,
    phase:  str,
    deck_profile: dict,
) -> float:
    """
    Compute concept-weighted total advantage for one action.

    Returns a float in roughly the same scale as policy._score()
    (0 to ~10, occasionally higher for high-synergy moves).
    """
    try:
        archetype = deck_profile.get("archetype", "setup_midrange") if deck_profile else "setup_midrange"
        weights   = get_weights(archetype, phase)

        evaluators = {
            "card_adv":           evaluate_card_advantage,
            "board_adv":          evaluate_board_advantage,
            "energy_adv":         evaluate_energy_advantage,
            "tempo_adv":          evaluate_tempo_advantage,
            "prize_adv":          evaluate_prize_advantage,
            "resource_adv":       evaluate_resource_advantage,
            "info_adv":           evaluate_info_advantage,
            "risk_reduction_adv": evaluate_risk_reduction,
        }

        total = 0.0
        for key, fn in evaluators.items():
            raw = fn(action, state, knowledge)
            total += raw * weights.get(key, 1.0)

        return total / SCALE

    except Exception:
        return 0.0


def breakdown(
    action: dict,
    state:  dict,
    knowledge,
    phase:  str,
    deck_profile: dict,
) -> dict:
    """Return per-adv-type breakdown dict (for logging)."""
    try:
        archetype = deck_profile.get("archetype", "setup_midrange") if deck_profile else "setup_midrange"
        weights   = get_weights(archetype, phase)

        fns = [
            ("card_adv",           evaluate_card_advantage),
            ("board_adv",          evaluate_board_advantage),
            ("energy_adv",         evaluate_energy_advantage),
            ("tempo_adv",          evaluate_tempo_advantage),
            ("prize_adv",          evaluate_prize_advantage),
            ("resource_adv",       evaluate_resource_advantage),
            ("info_adv",           evaluate_info_advantage),
            ("risk_reduction_adv", evaluate_risk_reduction),
        ]
        result = {}
        for key, fn in fns:
            raw = fn(action, state, knowledge)
            result[key] = round(raw * weights.get(key, 1.0) / SCALE, 3)
        result["total"] = round(sum(result.values()), 3)
        return result
    except Exception:
        return {}
