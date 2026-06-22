"""
Card metadata enrichment.

Provides cached card info lookup from cg.api for use in state normalization
and damage prediction.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

_CARD_CACHE: Dict[int, dict] = {}
_ATTACK_CACHE: Dict[int, dict] = {}
_LOADED = False
_LOAD_ERROR: Optional[str] = None


def _safe_id(obj, *attrs) -> Optional[int]:
    for attr in attrs:
        val = getattr(obj, attr, None)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    return None


def _ensure_loaded():
    global _LOADED, _LOAD_ERROR
    if _LOADED:
        return
    try:
        from cg.api import all_card_data, all_attack
        for c in all_card_data():
            cid = _safe_id(c, "cardId", "id")
            if cid is None:
                continue
            _CARD_CACHE[cid] = {
                "card_id": cid,
                "name": getattr(c, "name", "") or "",
                "card_type": str(getattr(c, "cardType", "unknown") or "unknown"),
                "hp": getattr(c, "hp", 0) or 0,
                "is_ex": bool(getattr(c, "ex", False)),
                "is_basic": bool(getattr(c, "basic", False)),
                "is_stage1": bool(getattr(c, "stage1", False)),
                "is_stage2": bool(getattr(c, "stage2", False)),
                "weakness": str(c.weakness) if getattr(c, "weakness", None) is not None else None,
                "resistance": str(c.resistance) if getattr(c, "resistance", None) is not None else None,
                "energy_type": str(c.energyType) if getattr(c, "energyType", None) is not None else None,
                "retreat_cost": getattr(c, "retreatCost", 0) or 0,
                "evolves_from": getattr(c, "evolvesFrom", None),
                "attack_ids": list(getattr(c, "attacks", None) or []),
                "abilities": [{"name": getattr(s, "name", ""), "text": getattr(s, "text", "")}
                              for s in (getattr(c, "skills", None) or [])],
            }
        for a in all_attack():
            aid = _safe_id(a, "attackId", "id")
            if aid is None:
                continue
            _ATTACK_CACHE[aid] = {
                "attack_id": aid,
                "name": getattr(a, "name", "") or "",
                "damage": getattr(a, "damage", 0) or 0,
                "text": getattr(a, "text", "") or "",
                "energies": [str(e) for e in (getattr(a, "energies", None) or [])],
            }
    except Exception as e:
        _LOAD_ERROR = str(e)
    _LOADED = True


def get_load_error() -> Optional[str]:
    _ensure_loaded()
    return _LOAD_ERROR


def get_card_metadata(card_id: int) -> Optional[dict]:
    _ensure_loaded()
    return _CARD_CACHE.get(card_id)


def get_attack_info(attack_id: int) -> Optional[dict]:
    _ensure_loaded()
    return _ATTACK_CACHE.get(attack_id)


def enrich_pokemon(pokemon: dict) -> dict:
    """Add card metadata to a normalized pokemon dict. Safe for missing data."""
    if not isinstance(pokemon, dict) or not pokemon:
        return pokemon

    cid_raw = pokemon.get("card_id") or pokemon.get("id")
    if cid_raw is None:
        return pokemon

    try:
        cid = int(cid_raw)
    except (ValueError, TypeError):
        return pokemon

    meta = get_card_metadata(cid)
    if not meta:
        pokemon.setdefault("name", "")
        pokemon.setdefault("is_ex", False)
        pokemon.setdefault("is_basic", True)
        pokemon.setdefault("stage", "basic")
        pokemon.setdefault("card_type", "unknown")
        pokemon.setdefault("weakness", None)
        pokemon.setdefault("resistance", None)
        pokemon.setdefault("attacks", [])
        pokemon.setdefault("abilities", [])
        pokemon.setdefault("retreat_cost", 0)
        return pokemon

    pokemon.setdefault("name", meta["name"])
    pokemon["is_ex"] = meta["is_ex"]
    pokemon["is_basic"] = meta["is_basic"]
    pokemon["is_stage1"] = meta.get("is_stage1", False)
    pokemon["is_stage2"] = meta.get("is_stage2", False)
    pokemon["stage"] = "basic" if meta["is_basic"] else ("stage1" if meta.get("is_stage1") else "stage2")
    pokemon["card_type"] = meta.get("card_type", "unknown")
    pokemon["weakness"] = meta["weakness"]
    pokemon["resistance"] = meta["resistance"]
    pokemon["energy_type"] = meta.get("energy_type")
    pokemon["retreat_cost"] = meta["retreat_cost"]
    pokemon["evolves_from"] = meta.get("evolves_from")
    pokemon["abilities"] = meta["abilities"]

    attacks = []
    for aid in meta.get("attack_ids", []):
        ainfo = get_attack_info(aid)
        if ainfo:
            attacks.append(ainfo)
    pokemon["attacks"] = attacks

    return pokemon
