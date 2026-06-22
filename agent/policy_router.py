"""
Policy mode router.

Determines whether to use rule_based, hybrid, or ml policy.
Default: rule_based. Controlled by env var POKEMON_AI_POLICY_MODE.
"""
import os

_VALID_MODES = {"rule_based", "hybrid", "ml"}
_DEFAULT_MODE = "rule_based"


def get_policy_mode() -> str:
    mode = os.environ.get("POKEMON_AI_POLICY_MODE", _DEFAULT_MODE).lower()
    return mode if mode in _VALID_MODES else _DEFAULT_MODE


def should_use_ml_policy() -> bool:
    return get_policy_mode() == "ml"


def should_use_hybrid_policy() -> bool:
    return get_policy_mode() in ("hybrid", "ml")
