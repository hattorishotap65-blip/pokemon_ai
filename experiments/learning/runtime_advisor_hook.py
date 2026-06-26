"""
Runtime hook for learned weight advisor.

Default off. Enable with POKEMON_AI_USE_LEARNED_WEIGHTS=1.
Falls back to None on any error so the caller uses existing logic.
"""
from __future__ import annotations
import os
from typing import Dict, List, Optional

_ENABLED_VAR = "POKEMON_AI_USE_LEARNED_WEIGHTS"
_WEIGHTS_VAR = "POKEMON_AI_WEIGHTS_PATH"
_FALLBACK_VAR = "POKEMON_AI_WEIGHTS_FALLBACK_PATH"
_DEFAULT_WEIGHTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "params", "raging_ogerpon_default.json",
)

_cached_weights: Optional[Dict[str, float]] = None
_cache_loaded: bool = False


def learned_weight_advisor_enabled() -> bool:
    return os.environ.get(_ENABLED_VAR) == "1"


def _load_weights_once() -> Dict[str, float]:
    global _cached_weights, _cache_loaded
    if _cache_loaded:
        return _cached_weights or {}
    _cache_loaded = True
    try:
        from experiments.learning.weight_profile import load_weight_profile
        path = os.environ.get(_WEIGHTS_VAR) or _DEFAULT_WEIGHTS
        fallback = os.environ.get(_FALLBACK_VAR) or _DEFAULT_WEIGHTS
        _cached_weights = load_weight_profile(path, fallback)
    except Exception:
        _cached_weights = {}
    return _cached_weights or {}


def reset_cache():
    """Reset cached weights (for testing)."""
    global _cached_weights, _cache_loaded
    _cached_weights = None
    _cache_loaded = False


def maybe_rank_with_learned_weights(
    state: dict, candidates: list
) -> Optional[List[dict]]:
    """Rank candidates using learned weights if enabled.

    Returns ranked list or None (caller should fall back to existing logic).
    """
    if not learned_weight_advisor_enabled():
        return None
    if not candidates:
        return None

    try:
        weights = _load_weights_once()
        if not weights:
            return None

        from experiments.learning.decision_advisor import rank_candidates
        ranked = rank_candidates(state or {}, candidates, weights)
        if not ranked:
            return None
        if max(r.get("score", 0.0) for r in ranked) <= 0.0:
            return None
        return ranked
    except Exception:
        return None
