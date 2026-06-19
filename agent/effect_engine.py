"""
Card effect data loader and utility functions for Iono's Lightning deck.

Provides structured access to card effects without overriding simulator legality.
The simulator's legal actions remain the source of truth; this module is for
scoring, fallback evaluation, and estimated damage.

Engine contract:
  - is_attack_option()  → type==13 and attackId is not None
  - is_retreat_option() → type==12
  - is_ability_option() → type==10
  - is_end_option()     → type==14
  - estimate_attack_damage() uses official JSON text (simulator_override.enabled=false)
"""
import json
import os
from typing import Optional

_EFFECTS: dict = {}

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data",
    "card_effects_iono_lightning_recommended_en_ja.json",
)
_KAGGLE_PATH = "/kaggle_simulations/agent/data/card_effects_iono_lightning_recommended_en_ja.json"

_IONO_POKEMON_IDS = {265, 268, 269, 270, 271}
_LIGHTNING_ENERGY_ID = 4

# OptionType constants (cabt API)
_OT_ABILITY = 10
_OT_RETREAT = 12
_OT_ATTACK  = 13
_OT_END     = 14


# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------

def load_card_effects(path: str = None) -> dict:
    """Load and cache card effects from JSON. Returns the cards sub-dict."""
    global _EFFECTS
    if _EFFECTS:
        return _EFFECTS
    for p in filter(None, [path, _DATA_PATH, _KAGGLE_PATH]):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            _EFFECTS = data.get("cards", {})
            return _EFFECTS
        except Exception:
            continue
    _EFFECTS = {}
    return _EFFECTS


def get_card_effect(card_id: int) -> dict:
    """Return effect entry for a card ID, or empty dict."""
    load_card_effects()
    return _EFFECTS.get(str(card_id), {})


def get_card_name(card_id: int) -> str:
    """Return English name for a card ID."""
    return get_card_effect(card_id).get("name_en", str(card_id))


# ---------------------------------------------------------------------------
# Option type classification — delegates to turn_rule_engine (single source)
# ---------------------------------------------------------------------------

try:
    from agent.turn_rule_engine import (
        is_attack_option,
        is_ability_option,
        is_retreat_option,
        is_end_option,
    )
except ImportError:
    def is_attack_option(opt: dict) -> bool:  # type: ignore[misc]
        return opt.get("type") == _OT_ATTACK and opt.get("attackId") is not None

    def is_ability_option(opt: dict) -> bool:  # type: ignore[misc]
        return opt.get("type") == _OT_ABILITY

    def is_retreat_option(opt: dict) -> bool:  # type: ignore[misc]
        return opt.get("type") == _OT_RETREAT

    def is_end_option(opt: dict) -> bool:  # type: ignore[misc]
        return opt.get("type") == _OT_END


# ---------------------------------------------------------------------------
# State accessors
# ---------------------------------------------------------------------------

def get_own_player(state: dict) -> dict:
    return state or {}


def get_own_active(state: dict) -> Optional[dict]:
    return state.get("active_pokemon") or None


def own_active_and_bench(state: dict) -> list:
    """Return list of own Pokemon dicts (active + bench, excluding None)."""
    result = []
    active = get_own_active(state)
    if active:
        result.append(active)
    result.extend(p for p in (state.get("bench") or []) if p)
    return result


def get_card_id(card) -> Optional[int]:
    """Extract integer card ID from a card dict, object, or raw int/str."""
    if card is None:
        return None
    if isinstance(card, int):
        return card
    if isinstance(card, dict):
        for key in ("card_id", "id", "cardId"):
            v = card.get(key)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return None
    for attr in ("card_id", "id", "cardId"):
        v = getattr(card, attr, None)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    try:
        return int(card)
    except (TypeError, ValueError):
        return None


def pokemon_energy_count(pokemon: dict) -> int:
    """Return energy count for a pokemon state dict."""
    if not pokemon:
        return 0
    n = pokemon.get("energy_count")
    if n is not None:
        try:
            return int(n)
        except (TypeError, ValueError):
            pass
    for key in ("energy_types", "energies"):
        v = pokemon.get(key)
        if isinstance(v, list):
            return len(v)
    return 0


def count_energy_in_play(state: dict, energy_id: int) -> int:
    """Count occurrences of energy_id attached to own Pokemon (any position)."""
    total = 0
    eid_str = str(energy_id)
    for p in own_active_and_bench(state):
        for key in ("energy_types", "energies"):
            energies = p.get(key)
            if isinstance(energies, list):
                for e in energies:
                    try:
                        if str(int(e)) == eid_str:
                            total += 1
                    except (TypeError, ValueError):
                        pass
                break
    return total


def count_lightning_on_iono_pokemon(state: dict) -> int:
    """Count Lightning energy on all own Iono's Pokemon (drives Voltorb damage)."""
    total = 0
    eid_str = str(_LIGHTNING_ENERGY_ID)
    for p in own_active_and_bench(state):
        cid = p.get("card_id")
        try:
            if int(cid) not in _IONO_POKEMON_IDS:
                continue
        except (TypeError, ValueError):
            continue
        for key in ("energy_types", "energies"):
            energies = p.get(key)
            if isinstance(energies, list):
                for e in energies:
                    try:
                        if str(int(e)) == eid_str:
                            total += 1
                    except (TypeError, ValueError):
                        pass
                break
    return total


# ---------------------------------------------------------------------------
# Damage estimation (official card text, simulator_override.enabled=false)
# ---------------------------------------------------------------------------

def estimate_attack_damage(card_id: int, state: dict) -> tuple:
    """
    Estimate damage for the given attacker card_id using official card text.

    Returns (damage: int, reason: str).
    """
    if card_id == 265:  # Iono's Voltorb: 20 + 20 * Lightning on Iono's Pokemon
        n = count_lightning_on_iono_pokemon(state)
        return 20 + 20 * n, f"voltorb_scaled_{n}_lightning"

    if card_id == 269:  # Iono's Bellibolt ex: official text LLLC → fixed 230
        return 230, "bellibolt_official_lllc_230"

    if card_id == 271:  # Iono's Kilowattrel: fixed 70
        return 70, "kilowattrel_fixed_70"

    # Generic fallback: read from JSON
    effect = get_card_effect(card_id)
    for atk in (effect.get("attacks") or []):
        dmg_info = atk.get("damage", {})
        fixed = dmg_info.get("fixed")
        if fixed is not None:
            return int(fixed), "json_fixed"
        base = dmg_info.get("base")
        if base is not None:
            return int(base), "json_base"
    return 0, "unknown"
