"""
Build rich advisor candidates from runtime LucarioPolicy options.

Extracts card names, action types, and game state so the learned
weight advisor can produce meaningful scores.
"""
from __future__ import annotations
from typing import Dict, List, Optional


def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _card_name_from_table(card_table: dict, card_id: int) -> str:
    data = card_table.get(card_id)
    if data:
        return _safe_attr(data, "name", "") or str(card_id)
    return str(card_id)


def _safe_card_name(policy, option) -> str:
    """Extract card name from an option, if possible."""
    try:
        from cg.api import AreaType
        area = _safe_attr(option, "area")
        index = _safe_attr(option, "index")
        player_index = _safe_attr(option, "playerIndex", policy.my_index)

        if area is None or index is None:
            return ""

        card = None
        try:
            from main import get_card
            card = get_card(policy.obs, area, index, player_index)
        except Exception:
            pass

        if card is None:
            return ""

        card_id = _safe_attr(card, "id", 0)
        if not card_id:
            return ""

        from main import card_table
        return _card_name_from_table(card_table, card_id)
    except Exception:
        return ""


def _attack_name(policy, option) -> str:
    """Get attack name from attackId."""
    try:
        attack_id = _safe_attr(option, "attackId")
        if not attack_id:
            return ""
        try:
            from cg.api import all_attack
            for atk in all_attack():
                if _safe_attr(atk, "attackId") == attack_id:
                    name = _safe_attr(atk, "name", "")
                    if name:
                        return name
        except Exception:
            pass
        return "attack_%s" % attack_id
    except Exception:
        return ""


def _infer_option_type(option) -> str:
    """Map OptionType enum to learning action type string."""
    try:
        from cg.api import OptionType
        otype = _safe_attr(option, "type")
        if otype is None:
            return "unknown"

        _MAP = {
            getattr(OptionType, "ATTACK", None): "attack",
            getattr(OptionType, "ABILITY", None): "ability",
            getattr(OptionType, "RETREAT", None): "retreat",
            getattr(OptionType, "ATTACH", None): "attach",
            getattr(OptionType, "EVOLVE", None): "evolve",
            getattr(OptionType, "END", None): "end",
            getattr(OptionType, "PLAY", None): "play",
            getattr(OptionType, "YES", None): "choice",
            getattr(OptionType, "NO", None): "choice",
            getattr(OptionType, "NUMBER", None): "choice",
            getattr(OptionType, "CARD", None): "choice",
            getattr(OptionType, "ENERGY_CARD", None): "choice",
            getattr(OptionType, "ENERGY", None): "choice",
        }
        _MAP.pop(None, None)
        return _MAP.get(otype, "unknown")
    except Exception:
        pass
    return "unknown"


def _refine_play_type(card_name: str, policy, option) -> str:
    """Refine 'play' into supporter/item/play_pokemon using card data."""
    try:
        from cg.api import CardType
        area = _safe_attr(option, "area")
        index = _safe_attr(option, "index")
        player_index = _safe_attr(option, "playerIndex", policy.my_index)

        if area is None or index is None:
            return "play_pokemon"

        from main import get_card, card_table
        card = get_card(policy.obs, area, index, player_index)
        if card is None:
            return "play_pokemon"

        card_id = _safe_attr(card, "id", 0)
        data = card_table.get(card_id)
        if data is None:
            return "play_pokemon"

        ctype = _safe_attr(data, "cardType")
        ct_supporter = getattr(CardType, "SUPPORTER", None)
        ct_item = getattr(CardType, "ITEM", None)
        ct_tool = getattr(CardType, "TOOL", None)
        ct_stadium = getattr(CardType, "STADIUM", None)
        ct_pokemon = getattr(CardType, "POKEMON", None)

        if ct_supporter is not None and ctype == ct_supporter:
            return "supporter"
        if ct_item is not None and ctype == ct_item:
            return "item"
        if ct_tool is not None and ctype == ct_tool:
            return "item"
        if ct_stadium is not None and ctype == ct_stadium:
            return "stadium"
        if ct_pokemon is not None and ctype == ct_pokemon:
            return "play_pokemon"
        return "trainer"
    except Exception:
        return "play_pokemon"


def build_runtime_candidate(policy, option, index: int) -> dict:
    """Build a learning-format candidate from a runtime option."""
    base_type = _infer_option_type(option)
    card_name = _safe_card_name(policy, option)
    atk_name = ""

    if base_type == "attack":
        atk_name = _attack_name(policy, option)

    if base_type == "play" and card_name:
        base_type = _refine_play_type(card_name, policy, option)

    if base_type == "attack" and atk_name:
        label = atk_name
        aid = "attack_%s" % atk_name.lower().replace(" ", "_").replace("'", "")
    elif card_name:
        label = card_name
        aid = "%s_%s" % (base_type, card_name.lower().replace(" ", "_").replace("'", ""))
    else:
        label = base_type
        aid = "%s_%d" % (base_type, index)

    return {
        "id": aid[:60],
        "label": label,
        "type": base_type,
        "original_index": index,
    }


def build_runtime_candidates(policy) -> list:
    """Build learning-format candidates for all runtime options."""
    result = []
    options = _safe_attr(policy.select, "option") or []
    for i, opt in enumerate(options):
        try:
            result.append(build_runtime_candidate(policy, opt, i))
        except Exception:
            result.append({"id": "opt_%d" % i, "label": "unknown", "type": "unknown", "original_index": i})
    return result


def build_runtime_state(policy) -> dict:
    """Build a learning-format state dict from runtime policy."""
    try:
        from main import card_table

        def _pokemon_name(p):
            if p is None:
                return ""
            pid = _safe_attr(p, "id", 0)
            return _card_name_from_table(card_table, pid) if pid else ""

        def _pokemon_names(lst):
            return [_pokemon_name(p) for p in (lst or []) if p is not None]

        def _card_names(lst):
            names = []
            for c in (lst or []):
                cid = _safe_attr(c, "id", 0)
                if cid:
                    names.append(_card_name_from_table(card_table, cid))
            return names

        me = policy.me
        opp = policy.opponent

        active_pokemon = (me.active or [None])[0] if me.active else None
        opp_active = (opp.active or [None])[0] if opp.active else None

        return {
            "active": _pokemon_name(active_pokemon),
            "bench": _pokemon_names(me.bench),
            "hand": _card_names(me.hand),
            "discard": _card_names(me.discard),
            "prizes_remaining": len(me.prize) if me.prize else 0,
            "opponent_active": _pokemon_name(opp_active),
            "opponent_bench": _pokemon_names(opp.bench),
            "opponent_prizes": len(opp.prize) if opp.prize else 0,
        }
    except Exception:
        return {}
