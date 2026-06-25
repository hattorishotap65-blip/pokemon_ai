"""
Weighted action evaluator.

Scores candidate actions using weights * features dot product.
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional, Tuple

from experiments.learning.action_features import extract_action_features


def load_weights(path: str) -> Dict[str, float]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_weights(weights: Dict[str, float], path: str):
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2, ensure_ascii=False)


def score_action(action: dict, state: dict, all_actions: list,
                 weights: Dict[str, float]) -> float:
    """Score a single action using weights * features."""
    features = extract_action_features(action, state, all_actions)
    score = 0.0
    for name, value in features.items():
        score += weights.get(name, 0.0) * value
    return score


def rank_actions(actions: list, state: dict,
                 weights: Dict[str, float]) -> List[Tuple[str, float]]:
    """Score and rank all actions. Returns [(action_id, score), ...] descending."""
    scored = []
    for action in actions:
        s = score_action(action, state, actions, weights)
        scored.append((action.get("id", ""), s))
    scored.sort(key=lambda x: -x[1])
    return scored


def evaluate_log_entry(entry: dict, weights: Dict[str, float]) -> dict:
    """Evaluate a single log entry. Returns ranking info."""
    actions = entry.get("legal_actions", [])
    state = entry.get("state", {})
    chosen_id = entry.get("chosen_action_id", "")

    if not actions or not chosen_id:
        return {"match": False, "rank": -1, "n_actions": len(actions)}

    ranked = rank_actions(actions, state, weights)
    predicted_id = ranked[0][0] if ranked else ""

    chosen_rank = -1
    for i, (aid, _) in enumerate(ranked):
        if aid == chosen_id:
            chosen_rank = i + 1
            break

    return {
        "match": predicted_id == chosen_id,
        "rank": chosen_rank,
        "n_actions": len(actions),
        "predicted_id": predicted_id,
        "chosen_id": chosen_id,
    }
