"""
turn_rule_engine.py

A small, deck-agnostic Pokémon TCG turn-rule layer for the Limited Card Battle agent.

Purpose:
- Separate core turn-flow rules from card-specific effects and deck-specific strategy.
- Treat the simulator's select.option as the source of truth for legal actions.
- Correctly distinguish Attack / Ability / Retreat / End.
- Prevent common policy mistakes:
  - treating Retreat as Attack
  - ending the turn while a legal attack exists
  - retreating while a legal attack exists
  - treating Ability as a turn-ending action

Important:
- This module does not decide whether an action is legal. The simulator does.
- This module only classifies already-present legal options and adds rule-level safety scoring.
- Card-specific value, damage, search targets, and combo logic should live in effect_engine.py / ionos_rules.py.
"""

from __future__ import annotations

import json as _json
import os as _os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

# -- Weights (loaded once from data/weights.json) ----------------------------
_LEGAL_ATTACK_SCORE_DEFAULT = 150.0
_legal_attack_score: float = _LEGAL_ATTACK_SCORE_DEFAULT

def _load_turn_rule_weights():
    global _legal_attack_score
    for p in (
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "data", "weights.json"),
        "/kaggle_simulations/agent/data/weights.json",
    ):
        try:
            with open(p, encoding="utf-8") as f:
                data = _json.load(f)
            _legal_attack_score = float(data.get("legal_attack_score", _LEGAL_ATTACK_SCORE_DEFAULT))
            return
        except Exception:
            continue

_load_turn_rule_weights()

# ---------------------------------------------------------------------------
# Option type constants observed in the simulator logs
# ---------------------------------------------------------------------------

OPTION_ABILITY = 10
OPTION_RETREAT = 12
OPTION_ATTACK = 13
OPTION_END = 14

# Common non-turn-ending action types seen or expected in this simulator.
# Keep these as soft classifications. The simulator remains the legal source of truth.
OPTION_ENERGY_ATTACH = 8


# ---------------------------------------------------------------------------
# Basic option classification
# ---------------------------------------------------------------------------

def option_type(opt: Dict[str, Any]) -> Optional[int]:
    """Safely return option type."""
    if not isinstance(opt, dict):
        return None
    try:
        return int(opt.get("type"))
    except Exception:
        return None


def is_attack_option(opt: Dict[str, Any]) -> bool:
    """
    Attack = type 13 AND attackId exists.

    Never treat type 12 as attack.
    """
    if not isinstance(opt, dict):
        return False
    return option_type(opt) == OPTION_ATTACK and opt.get("attackId") is not None


def is_ability_option(opt: Dict[str, Any]) -> bool:
    """Ability = type 10."""
    return isinstance(opt, dict) and option_type(opt) == OPTION_ABILITY


def is_retreat_option(opt: Dict[str, Any]) -> bool:
    """Retreat / switch active by retreat = type 12."""
    return isinstance(opt, dict) and option_type(opt) == OPTION_RETREAT


def is_end_option(opt: Dict[str, Any]) -> bool:
    """End turn = type 14."""
    return isinstance(opt, dict) and option_type(opt) == OPTION_END


def is_energy_attach_option(opt: Dict[str, Any]) -> bool:
    """Manual or effect-based energy attachment option, when exposed as type 8."""
    return isinstance(opt, dict) and option_type(opt) == OPTION_ENERGY_ATTACH


def is_turn_ending_option(opt: Dict[str, Any]) -> bool:
    """
    In normal Pokémon TCG flow, Attack and End are turn-ending decisions.

    Ability is not turn-ending.
    Retreat is not inherently turn-ending, although it can change the active Pokémon.
    Items / Supporters / Stadiums / Energy attachments are also not inherently turn-ending.
    """
    return is_attack_option(opt) or is_end_option(opt)


def can_continue_after_option(opt: Dict[str, Any]) -> bool:
    """
    Whether the turn can continue after selecting this option, by core turn-flow rules.

    The simulator still controls the actual next select.
    """
    return not is_turn_ending_option(opt)


# ---------------------------------------------------------------------------
# Select helpers
# ---------------------------------------------------------------------------

def get_options(select: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(select, dict):
        return []
    opts = select.get("option") or []
    return [o for o in opts if isinstance(o, dict)]


def get_legal_attack_options(select: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [o for o in get_options(select) if is_attack_option(o)]


def has_legal_attack_option(select: Optional[Dict[str, Any]]) -> bool:
    return bool(get_legal_attack_options(select))


def get_ability_options(select: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [o for o in get_options(select) if is_ability_option(o)]


def get_retreat_options(select: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [o for o in get_options(select) if is_retreat_option(o)]


def get_end_options(select: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [o for o in get_options(select) if is_end_option(o)]


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def get_own_player(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}

    players = state.get("players") or []
    your_index = state.get("yourIndex", 0)

    try:
        your_index = int(your_index)
    except Exception:
        your_index = 0

    if isinstance(players, list) and 0 <= your_index < len(players):
        player = players[your_index]
        if isinstance(player, dict):
            return player

    return {}


def get_own_active(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    player = get_own_player(state)
    active = player.get("active") or []

    if isinstance(active, list) and active:
        card = active[0]
        return card if isinstance(card, dict) else None

    if isinstance(active, dict):
        return active

    return None


def get_own_bench(state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    player = get_own_player(state)
    bench = player.get("bench") or []
    if not isinstance(bench, list):
        return []
    return [c for c in bench if isinstance(c, dict)]


def own_active_and_bench(state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    active = get_own_active(state)
    if active is not None:
        cards.append(active)
    cards.extend(get_own_bench(state))
    return cards


def get_card_id(card: Any) -> Optional[int]:
    try:
        if isinstance(card, dict):
            raw = card.get("id", card.get("card_id", None))
            return int(raw) if raw is not None else None
        return int(card)
    except Exception:
        return None


def get_card_name(card: Any) -> str:
    if isinstance(card, dict):
        return str(card.get("name") or card.get("card_name") or "")
    return ""


def pokemon_energy_cards(pokemon: Optional[Dict[str, Any]]) -> List[Any]:
    if not isinstance(pokemon, dict):
        return []

    for key in ("energyCards", "energies", "energy_types", "attachedEnergy", "attached_energy"):
        value = pokemon.get(key)
        if isinstance(value, list):
            return value

    return []


def pokemon_energy_count(pokemon: Optional[Dict[str, Any]]) -> int:
    return len(pokemon_energy_cards(pokemon))


def has_active_energy(state: Optional[Dict[str, Any]]) -> bool:
    return pokemon_energy_count(get_own_active(state)) > 0


# ---------------------------------------------------------------------------
# Rule-context and scoring
# ---------------------------------------------------------------------------

@dataclass
class TurnRuleContext:
    has_attack: bool
    attack_count: int
    ability_count: int
    retreat_count: int
    end_count: int
    active_id: Optional[int]
    active_name: str
    active_energy_count: int


def build_turn_rule_context(
    state: Optional[Dict[str, Any]],
    select: Optional[Dict[str, Any]],
) -> TurnRuleContext:
    active = get_own_active(state)
    attacks = get_legal_attack_options(select)
    abilities = get_ability_options(select)
    retreats = get_retreat_options(select)
    ends = get_end_options(select)

    return TurnRuleContext(
        has_attack=bool(attacks),
        attack_count=len(attacks),
        ability_count=len(abilities),
        retreat_count=len(retreats),
        end_count=len(ends),
        active_id=get_card_id(active),
        active_name=get_card_name(active),
        active_energy_count=pokemon_energy_count(active),
    )


def _has_play_basic_option(select: Optional[Dict[str, Any]]) -> bool:
    """True when a PLAY (type=7) option exists.

    In cabt, PLAY (type=7) is exclusively for placing a Basic Pokemon
    from hand onto the bench. Trainers/Supporters/Energy use type 3/4/5/8.
    """
    return any(option_type(o) == 7 for o in get_options(select))


def _empty_bench_loss_risk(state: Optional[Dict[str, Any]], select: Optional[Dict[str, Any]]) -> bool:
    """True when bench is empty and a PLAY Basic option is available."""
    if not isinstance(state, dict):
        return False
    if get_own_bench(state):
        return False
    return _has_play_basic_option(select)


def _opp_final_prize_active_is_ex(state: Optional[Dict[str, Any]]) -> bool:
    """True when opponent has <=2 prizes left and our active is an ex."""
    if not isinstance(state, dict):
        return False
    opp_prizes = int(state.get("opponent", {}).get("prizes_remaining", 6) or 6)
    if opp_prizes > 2:
        return False
    active = get_own_active(state)
    if not active:
        return False
    name = get_card_name(active).lower()
    return " ex" in name or name.endswith(" ex")


def rule_score_option(
    opt: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    select: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    """
    Return a small rule-level score/penalty and reason.

    This is intentionally deck-agnostic. Card-specific scoring should be added
    by effect_engine.py / ionos_rules.py / policy.py after this.
    """
    ctx = build_turn_rule_context(state, select)

    # --- A. Empty bench loss prevention ---
    if _empty_bench_loss_risk(state, select):
        if is_attack_option(opt) or is_end_option(opt):
            return -500.0, "turn_rule:empty_bench_play_basic_first"

    # --- B. Opponent final prize survival ---
    _final_prize_ex_risk = _opp_final_prize_active_is_ex(state)
    if _final_prize_ex_risk:
        bench = get_own_bench(state)
        _has_non_ex_bench = any(
            " ex" not in get_card_name(c).lower() and not get_card_name(c).lower().endswith(" ex")
            for c in bench
        )
        if _has_non_ex_bench:
            if is_attack_option(opt):
                return -300.0, "turn_rule:ex_active_opp_final_prizes_retreat_first"
            if is_end_option(opt):
                return -400.0, "turn_rule:ex_active_opp_final_prizes_retreat_first"
            if is_retreat_option(opt):
                return 500.0, "turn_rule:retreat_ex_to_survive_final_prizes"

    if is_attack_option(opt):
        return _legal_attack_score, "turn_rule:legal_attack_is_turn_finisher"

    if is_end_option(opt):
        if ctx.has_attack:
            return -1000.0, "turn_rule:avoid_end_when_attack_available"
        if ctx.ability_count > 0:
            return -60.0, "turn_rule:avoid_end_when_ability_available"
        return -5.0, "turn_rule:end_only_if_no_useful_action"

    if is_retreat_option(opt):
        if ctx.has_attack:
            return -1000.0, "turn_rule:avoid_retreat_when_attack_available"
        if ctx.active_energy_count > 0:
            return -250.0, "turn_rule:avoid_retreat_losing_energy"
        return -40.0, "turn_rule:retreat_low_priority"

    if is_ability_option(opt):
        # Ability is not turn-ending. Do not overvalue it at the rule layer.
        # Card-specific logic may add a bonus if the ability enables attack,
        # increases damage, draws cards, or improves setup.
        if ctx.has_attack:
            return 5.0, "turn_rule:ability_before_attack_optional"
        return 15.0, "turn_rule:ability_can_continue_turn"

    if is_energy_attach_option(opt):
        # Energy attachment is normally useful but card-specific scoring should decide target value.
        if ctx.has_attack:
            return 0.0, "turn_rule:attach_optional_when_attack_available"
        return 10.0, "turn_rule:attach_can_continue_turn"

    return 0.0, "turn_rule:no_rule_adjustment"


def should_strongly_prefer_attack(
    state: Optional[Dict[str, Any]],
    select: Optional[Dict[str, Any]],
) -> bool:
    """
    Generic rule: if the simulator offers an attack, do not End or Retreat
    without a card-specific reason that is explicitly stronger.

    The policy layer can still choose a useful Ability before attacking.
    """
    return has_legal_attack_option(select)


def classify_option(opt: Dict[str, Any]) -> str:
    if is_attack_option(opt):
        return "attack"
    if is_ability_option(opt):
        return "ability"
    if is_retreat_option(opt):
        return "retreat"
    if is_end_option(opt):
        return "end"
    if is_energy_attach_option(opt):
        return "energy_attach"
    t = option_type(opt)
    return f"unknown_type_{t}" if t is not None else "unknown"


def option_debug_record(
    opt: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    select: Optional[Dict[str, Any]],
    score: Optional[float] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    active = get_own_active(state)
    ctx = build_turn_rule_context(state, select)

    return {
        "option_type": option_type(opt),
        "option_class": classify_option(opt),
        "attack_id": opt.get("attackId") if isinstance(opt, dict) else None,
        "is_attack": is_attack_option(opt),
        "is_ability": is_ability_option(opt),
        "is_retreat": is_retreat_option(opt),
        "is_end": is_end_option(opt),
        "is_turn_ending": is_turn_ending_option(opt),
        "can_continue_after": can_continue_after_option(opt),
        "has_legal_attack_option": ctx.has_attack,
        "active_id": get_card_id(active),
        "active_name": get_card_name(active),
        "active_energy_count": pokemon_energy_count(active),
        "rule_score": score,
        "rule_reason": reason,
    }


def select_summary(
    state: Optional[Dict[str, Any]],
    select: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    ctx = build_turn_rule_context(state, select)
    options = get_options(select)

    return {
        "turn_rule_context": asdict(ctx),
        "option_classes": [classify_option(o) for o in options],
        "has_legal_attack_option": ctx.has_attack,
        "must_not_treat_retreat_as_attack": True,
        "ability_is_not_turn_ending": True,
        "attack_and_end_are_turn_ending": True,
    }


__all__ = [
    "OPTION_ABILITY",
    "OPTION_RETREAT",
    "OPTION_ATTACK",
    "OPTION_END",
    "OPTION_ENERGY_ATTACH",
    "option_type",
    "is_attack_option",
    "is_ability_option",
    "is_retreat_option",
    "is_end_option",
    "is_energy_attach_option",
    "is_turn_ending_option",
    "can_continue_after_option",
    "get_options",
    "get_legal_attack_options",
    "has_legal_attack_option",
    "get_ability_options",
    "get_retreat_options",
    "get_end_options",
    "get_own_player",
    "get_own_active",
    "get_own_bench",
    "own_active_and_bench",
    "get_card_id",
    "get_card_name",
    "pokemon_energy_cards",
    "pokemon_energy_count",
    "has_active_energy",
    "TurnRuleContext",
    "build_turn_rule_context",
    "rule_score_option",
    "should_strongly_prefer_attack",
    "classify_option",
    "option_debug_record",
    "select_summary",
]
