"""
ML training data serializer.

Converts decision-point data (state, action, features, score) into
JSON-serializable dicts for imitation learning.
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional


def _safe_value(v: Any) -> Any:
    """Convert value to JSON-serializable form."""
    if v is None:
        return None
    if isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_safe_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _safe_value(val) for k, val in v.items()}
    if isinstance(v, set):
        return sorted(str(x) for x in v)
    return str(v)


def serialize_action(action: dict) -> dict:
    if not isinstance(action, dict):
        return {}
    return {
        "type": action.get("type"),
        "cardId": str(action.get("cardId") or ""),
        "attackId": action.get("attackId"),
        "index": action.get("index"),
        "area": action.get("area"),
        "playerIndex": action.get("playerIndex"),
        "inPlayArea": action.get("inPlayArea"),
        "inPlayIndex": action.get("inPlayIndex"),
    }


def serialize_state_summary(state: dict) -> dict:
    if not isinstance(state, dict):
        return {}
    ap = state.get("active_pokemon") or {}
    opp = state.get("opponent") or {}
    opp_ap = opp.get("active_pokemon") or {}
    return {
        "turn": state.get("turn", 0),
        "prizes_remaining": state.get("prizes_remaining", 6),
        "opponent_prizes_remaining": opp.get("prizes_remaining", 6),
        "my_active_cid": str(ap.get("card_id", "")),
        "my_active_hp": ap.get("hp_remaining", 0),
        "my_active_energy": ap.get("energy_count", 0),
        "my_active_is_ex": bool(ap.get("is_ex", False)),
        "opp_active_cid": str(opp_ap.get("card_id", "")),
        "opp_active_hp": opp_ap.get("hp_remaining", 0),
        "opp_active_is_ex": bool(opp_ap.get("is_ex", False)),
        "bench_count": len(state.get("bench") or []),
        "opp_bench_count": len(opp.get("bench") or []),
        "deck_count": state.get("deck_count", 0) or 0,
        "hand_count": state.get("hand_count", 0) or 0,
    }


def infer_deck_id(state: dict) -> str:
    if not isinstance(state, dict):
        return "unknown"
    for key in ("deck_id", "deckProfile", "deck_profile", "deck_name"):
        val = state.get(key)
        if val and isinstance(val, str):
            return val
    return "unknown"


def infer_opponent_deck_id(state: dict) -> str:
    if not isinstance(state, dict):
        return "unknown"
    opp = state.get("opponent") or {}
    for key in ("deck_id", "deckProfile", "deck_profile", "deck_name"):
        val = opp.get(key)
        if val and isinstance(val, str):
            return val
    return "unknown"


def compute_outcome_weight(game_result: str, winner: str = "") -> Optional[float]:
    if not game_result:
        return None
    r = str(game_result).lower().strip()
    if r in ("win", "won", "victory", "w"):
        return 1.0
    if r in ("loss", "lost", "defeat", "l"):
        return -1.0
    if r in ("draw", "tie", "d"):
        return 0.0
    return None


def make_training_example(
    state: dict,
    action: dict,
    selected: bool,
    score: float = 0.0,
    reason: str = "",
    breakdown: Optional[dict] = None,
    features: Optional[dict] = None,
    game_id: int = 0,
    decision_id: str = "",
    candidate_index: int = 0,
    deck_id: str = "",
    opponent_deck_id: str = "",
    game_result: str = "",
    winner: str = "",
    final_score: Optional[float] = None,
    prizes_taken: Optional[int] = None,
    opponent_prizes_taken: Optional[int] = None,
    turn_count: Optional[int] = None,
    safety_violation: Optional[bool] = None,
    outcome_weight: Optional[float] = None,
) -> dict:
    """Create one training example for a candidate action."""
    example = {
        "game_id": game_id,
        "decision_id": decision_id,
        "candidate_index": candidate_index,
        "selected": selected,
        "score": round(score, 4) if isinstance(score, float) else score,
        "reason": str(reason),
        "action": serialize_action(action),
        "state_summary": serialize_state_summary(state),
    }
    if features is not None:
        example["features"] = _safe_value(features)
    if breakdown is not None:
        example["breakdown"] = _safe_value(breakdown)

    if deck_id:
        example["deck_id"] = deck_id
    if opponent_deck_id:
        example["opponent_deck_id"] = opponent_deck_id

    outcome = {}
    if game_result:
        outcome["game_result"] = game_result
    if winner:
        outcome["winner"] = winner
    if final_score is not None:
        outcome["final_score"] = final_score
    if prizes_taken is not None:
        outcome["prizes_taken"] = prizes_taken
    if opponent_prizes_taken is not None:
        outcome["opponent_prizes_taken"] = opponent_prizes_taken
    if turn_count is not None:
        outcome["turn_count"] = turn_count
    if safety_violation is not None:
        outcome["safety_violation"] = safety_violation
    if outcome_weight is not None:
        outcome["outcome_weight"] = outcome_weight
    if outcome:
        example["outcome"] = outcome

    return example


def append_jsonl(path: str, example: dict) -> None:
    """Append one example as a JSON line."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(example, ensure_ascii=False) + "\n")


def write_jsonl(path: str, examples: List[dict]) -> None:
    """Write all examples as JSON lines."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
