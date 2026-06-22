"""
ML policy scoring scaffold.

Disabled by default. Returns 0.0 unless explicitly enabled via
configs/ml_policy_weights.json with enabled=true.
"""
from __future__ import annotations
import json
import os
from typing import Tuple

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CONFIG_PATH = os.path.join(_REPO_ROOT, "configs", "ml_policy_weights.json")

_LOADED = False
_ENABLED = False
_WEIGHTS: dict = {}


def _ensure_loaded():
    global _LOADED, _ENABLED, _WEIGHTS
    if _LOADED:
        return
    _LOADED = True
    env_path = os.environ.get("POKEMON_AI_ML_WEIGHTS_PATH")
    paths = [_CONFIG_PATH, "/kaggle_simulations/agent/configs/ml_policy_weights.json"]
    if env_path:
        paths = [env_path] + paths
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            _ENABLED = bool(data.get("enabled", False))
            _WEIGHTS = data.get("weights", {})
            return
        except Exception:
            continue


def is_ml_policy_enabled() -> bool:
    _ensure_loaded()
    return _ENABLED


def score_ml_policy(action: dict, state: dict) -> Tuple[float, str]:
    """Return ML-based score supplement. Default 0.0 when disabled."""
    _ensure_loaded()
    if not _ENABLED:
        return 0.0, ""
    if not _WEIGHTS:
        return 0.0, "ml_no_weights"

    try:
        from agent.ml_features import extract_features
        features = extract_features(state, action)
        score = 0.0
        for key, weight in _WEIGHTS.items():
            val = features.get(key)
            if val is None:
                continue
            if isinstance(val, bool):
                val = 1.0 if val else 0.0
            elif isinstance(val, (int, float)):
                val = float(val)
            else:
                continue
            score += val * float(weight)
        return score, "ml_linear"
    except Exception:
        return 0.0, "ml_error"
