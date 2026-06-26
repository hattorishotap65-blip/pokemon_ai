"""
Decision advisor: rank candidate actions using learned weights.

Bridges agent_action_adapter and evaluator to produce ranked
candidate lists with scores.
"""
from __future__ import annotations
from typing import Dict, List, Optional

from experiments.learning.agent_action_adapter import normalize_actions
from experiments.learning.evaluator import score_action


def rank_candidates(
    state: dict, candidates: list, weights: Dict[str, float]
) -> List[dict]:
    """Rank candidate actions by learned weight score.

    Returns list of dicts with action_id, score, original_index,
    normalized_action — sorted by score descending.
    """
    if not candidates or not isinstance(candidates, list):
        return []

    normalized = normalize_actions(candidates)
    scored = []
    for i, (orig, norm) in enumerate(zip(candidates, normalized)):
        s = score_action(norm, state or {}, normalized, weights or {})
        scored.append({
            "action_id": norm["id"],
            "score": s,
            "original_index": i,
            "normalized_action": norm,
        })

    scored.sort(key=lambda x: -x["score"])
    return scored


def choose_best_candidate(
    state: dict, candidates: list, weights: Dict[str, float]
) -> Optional[dict]:
    """Return the highest-scoring candidate, or None if empty."""
    ranked = rank_candidates(state, candidates, weights)
    return ranked[0] if ranked else None
