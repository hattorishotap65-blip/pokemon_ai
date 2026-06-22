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


def _ensure_loaded():
    global _LOADED
    if _LOADED:
        return
    try:
        from cg.api import all_card_data, all_attack
        for c in all_card_data():
            _CARD_CACHE[c.cardId] = {
                "card_id": c.cardId,
                "name": c.name or "",
                "card_type": str(c.cardType) if c.cardType is not None else "unknown",
                "hp": c.hp,
                "is_ex": bool(c.ex),
                "is_basic": bool(c.basic),
                "is_stage1": bool(c.stage1),
                "is_stage2": bool(c.stage2),
                "weakness": str(c.weakness) if c.weakness is not None else None,
                "resistance": str(c.resistance) if c.resistance is not None else None,
                "energy_type": str(c.energyType) if c.energyType is not None else None,
                "retreat_cost": c.retreatCost,
                "evolves_from": c.evolvesFrom,
                "attack_ids": list(c.attacks) if c.attacks else [],
                "abilities": [{"name": s.name, "text": s.text} for s in (c.skills or [])],
            }
        for a in all_attack():
            _ATTACK_CACHE[a.attackId] = {
                "attack_id": a.attackId,
                "name": a.name or "",
                "damage": a.damage,
                "text": a.text or "",
                "energies": [str(e) for e in (a.energies or [])],
            }
    except Exception:
        pass
    _LOADED = True


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
