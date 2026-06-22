"""
Pre-attack damage prediction.

Estimates damage before attacking, accounting for:
- Base damage (card-specific or from metadata)
- Weakness (x2)
- Resistance (-30)
- prevent_damage_from_ex (ability/effect text detection)

Usage:
    from agent.damage_predictor import predict_attack_damage
    result = predict_attack_damage(attacker, defender, state)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

_EX_REFERENCES = ["pokémon ex", "pokemon ex"]
_DAMAGE_PREVENTION_PHRASES = [
    "prevent that damage", "prevent all damage",
    "takes no damage", "no damage", "damage from attacks",
]

_RESISTANCE_VALUE = 30


def _detect_prevent_damage_from_ex(defender: dict) -> bool:
    """Check if defender has an ability/effect that prevents damage from ex.

    Requires BOTH an ex reference AND a damage prevention phrase in the same text.
    """
    texts = []
    for ability in (defender.get("abilities") or []):
        texts.append((ability.get("text") or "").lower())
    for attack in (defender.get("attacks") or []):
        texts.append((attack.get("text") or "").lower())

    for text in texts:
        has_ex_ref = any(ref in text for ref in _EX_REFERENCES)
        has_prevention = any(phrase in text for phrase in _DAMAGE_PREVENTION_PHRASES)
        if has_ex_ref and has_prevention:
            return True
    return False


def _get_raw_damage(attacker: dict, state: dict) -> int:
    """Get raw attack damage for the attacker."""
    cid_raw = attacker.get("card_id") or attacker.get("id")
    if cid_raw is None:
        return 0
    try:
        cid = int(cid_raw)
    except (ValueError, TypeError):
        return 0

    dmg = 0
    try:
        from agent.effect_engine import estimate_attack_damage
        dmg, _ = estimate_attack_damage(cid, state)
    except Exception:
        pass

    if dmg > 0:
        return dmg

    attacks = attacker.get("attacks") or []
    if attacks:
        return attacks[0].get("damage", 0) or 0
    return 0


def _types_match(atk_type: str, def_type: str) -> bool:
    if not atk_type or not def_type:
        return False
    return atk_type.lower().strip() == def_type.lower().strip()


def predict_attack_damage(
    attacker: dict, defender: dict, state: dict,
    attack: Optional[dict] = None,
) -> dict:
    """Predict damage before attacking.

    Args:
        attacker: normalized pokemon dict (own active)
        defender: normalized pokemon dict (opponent active)
        state: game state
        attack: specific attack dict (optional, uses first if None)

    Returns:
        dict with raw_damage, predicted_damage, can_damage, can_ko,
        weakness_applies, resistance_applies, damage_prevented, tags, reasons.
    """
    result = {
        "raw_damage": 0,
        "predicted_damage": 0,
        "can_damage": False,
        "can_ko": False,
        "weakness_applies": False,
        "resistance_applies": False,
        "damage_prevented": False,
        "tags": [],
        "reasons": [],
    }

    if not isinstance(attacker, dict) or not isinstance(defender, dict):
        result["reasons"].append("invalid_input")
        return result

    raw = _get_raw_damage(attacker, state)
    if attack and isinstance(attack, dict):
        raw = attack.get("damage", 0) or raw

    result["raw_damage"] = raw

    is_ex = attacker.get("is_ex", False)
    prevent_ex = _detect_prevent_damage_from_ex(defender)

    if is_ex and prevent_ex:
        result["damage_prevented"] = True
        result["predicted_damage"] = 0
        result["tags"].append("prevent_damage_from_ex")
        result["reasons"].append("defender prevents damage from ex")
        return result

    damage = raw

    atk_type = str(attacker.get("energy_type") or attacker.get("card_type") or "")
    def_weakness = str(defender.get("weakness") or "")
    def_resistance = str(defender.get("resistance") or "")

    if damage > 0 and _types_match(atk_type, def_weakness):
        damage *= 2
        result["weakness_applies"] = True
        result["tags"].append("weakness_x2")
        result["reasons"].append(f"weakness: {atk_type} vs {def_weakness}")

    if damage > 0 and _types_match(atk_type, def_resistance):
        damage = max(0, damage - _RESISTANCE_VALUE)
        result["resistance_applies"] = True
        result["tags"].append("resistance_minus30")
        result["reasons"].append(f"resistance: {atk_type} vs {def_resistance}")

    result["predicted_damage"] = damage
    result["can_damage"] = damage > 0

    def_hp = defender.get("hp_remaining", 9999) or 9999
    if damage >= def_hp and def_hp > 0:
        result["can_ko"] = True
        result["tags"].append("can_ko")

    return result


def _has_attack_energy(candidate: dict) -> bool:
    """Rough check: candidate has at least 1 energy attached."""
    return (candidate.get("energy_count", 0) or 0) >= 1


def find_alternative_attackers(
    state: dict, defender: dict,
) -> List[dict]:
    """Find bench Pokemon that can damage the defender when active cannot.

    Returns list of candidate dicts sorted by score (highest first).
    Uses only predicted damage / card properties, not opponent names.
    """
    bench = state.get("bench") or []
    if not isinstance(bench, list):
        return []

    candidates = []
    for i, poke in enumerate(bench):
        if not isinstance(poke, dict) or not poke:
            continue

        pred = predict_attack_damage(poke, defender, state)
        if not pred["can_damage"]:
            continue

        score = 0.0
        reasons = []

        if pred["can_ko"]:
            score += 800.0
            reasons.append("alternative_attacker_can_ko")
        else:
            score += 400.0
            reasons.append("alternative_attacker_can_damage")

        if not poke.get("is_ex", False):
            score += 100.0
            reasons.append("non_ex_attacker_preferred")

        if _has_attack_energy(poke):
            score += 200.0
            reasons.append("energy_ready")
        else:
            score -= 300.0
            reasons.append("energy_not_ready")

        hp = poke.get("hp_remaining", 0) or 0
        score += min(hp * 0.5, 100.0)

        candidates.append({
            "bench_index": i,
            "card_id": str(poke.get("card_id", "")),
            "name": poke.get("name", ""),
            "is_ex": poke.get("is_ex", False),
            "predicted_damage": pred["predicted_damage"],
            "can_damage": pred["can_damage"],
            "can_ko": pred["can_ko"],
            "energy_ready": _has_attack_energy(poke),
            "score": score,
            "reasons": reasons,
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def format_prediction(pred: dict) -> str:
    """Format prediction for log/reason output."""
    parts = [f"predicted_damage={pred['predicted_damage']}"]
    if pred["damage_prevented"]:
        parts.append("damage_prevented")
    parts.extend(pred["tags"])
    return "damage_predictor:" + "|".join(parts)
