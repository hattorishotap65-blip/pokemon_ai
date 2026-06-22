"""
Externalized parameter loader.

Reads scoring parameters from configs/params/default_params.json.
Falls back to hardcoded defaults if file is missing or unreadable.
"""
from __future__ import annotations
import json
import os
from typing import Any

_DEFAULTS = {
    "zero_damage_attack_penalty": 500.0,
    "ko_opponent_bonus": 20.0,
    "boss_can_ko": 30.0,
    "alt_attacker_ko_score": 800.0,
    "energy_ready_bonus": 200.0,
}

_PARAMS: dict = {}
_LOADED = False


def _ensure_loaded():
    global _LOADED, _PARAMS
    if _LOADED:
        return
    _PARAMS = dict(_DEFAULTS)
    for p in (
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "configs", "params", "default_params.json"),
        "/kaggle_simulations/agent/configs/params/default_params.json",
    ):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            for k in _DEFAULTS:
                if k in data:
                    _PARAMS[k] = float(data[k])
            break
        except Exception:
            continue
    _LOADED = True


def get(name: str) -> float:
    """Get parameter value. Falls back to hardcoded default."""
    _ensure_loaded()
    return _PARAMS.get(name, _DEFAULTS.get(name, 0.0))


def all_params() -> dict:
    """Return all loaded parameters."""
    _ensure_loaded()
    return dict(_PARAMS)
