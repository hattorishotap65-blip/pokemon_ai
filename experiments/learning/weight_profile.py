"""
Safe weight profile loader.

Loads learned weights JSON with fallback and error recovery.
"""
from __future__ import annotations
import json
import os
from typing import Dict, Optional


def load_weight_profile(
    path: str, fallback_path: Optional[str] = None
) -> Dict[str, float]:
    """Load weights from JSON. Falls back gracefully on errors."""
    for p in (path, fallback_path):
        if p is None or not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                continue
            weights = {}
            for k, v in raw.items():
                if isinstance(v, (int, float)):
                    weights[str(k)] = float(v)
            return weights
        except (json.JSONDecodeError, OSError, ValueError):
            continue
    return {}
