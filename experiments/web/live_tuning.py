"""Live Tuning Panel backend: session-only runtime parameter overrides.

This module never touches params.json or main.py. It holds a session-scoped
override dict and a few pure helper functions that server.py wires up to the
real agent/policy objects. Everything here is deliberately decoupled from
cg/sim so it can be unit-tested without the native cg library.

Functions:
    get_runtime_overrides() / set_runtime_override() / reset_runtime_overrides()
    validate_param_update()
    effective_params()
    suggest_params_for_live_review()
    build_tuning_preview()
    build_tuning_log_entry() / append_tuning_log()
"""
import json
import math
import os
import re
import time

DEFAULT_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "session_tuning_log.jsonl")

LABELS = ["human_better", "agent_better", "both_ok", "both_bad", "unclear"]
CONFIDENCES = ["high", "medium", "low"]

_PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Heuristic category/risk-flag -> related-param suggestions. Intentionally
# approximate ("heuristic mapping" per spec) -- callers should pass
# available_params so suggestions are filtered down to params that actually
# exist for the currently-loaded agent.
#
# Only params that actually move the agent's real decision are listed here.
# Two classes of params.json keys were ruled out by driving real games
# through server.py in WSL and reading raging_bolt/main.py directly:
#   - score_supporter_*/score_attack_*/score_item_*/score_retreat: these
#     look like per-card base scores but _score_attack()/_score_play() use
#     hardcoded Python constants instead, never self.p(...) -- dead.
#   - eval_*: read via self.p(...) inside evaluate_state(), but
#     choose_with_search() computes current_eval = self.evaluate_state()
#     and then never uses that variable again -- also dead, despite being
#     "live" by the self.p() definition.
# What actually reaches choose_with_search()'s final score is the impact_*
# family (via _estimate_action_impact) and the search_weight_* weights,
# plus the handful of score_* keys _score_play/_score_attack do read
# (score_play_pokemon_raging_bolt, score_play_pokemon_ogerpon,
# score_item_pokemon_catcher, score_item_unfair_stamp).
_CATEGORY_PARAM_SUGGESTIONS = {
    "no_next_attacker": [
        "impact_crispin_per_energy", "impact_crispin_bolt_bonus",
        "impact_energy_retrieval_per", "impact_attach_bt_req", "search_weight_future",
    ],
    "boss_missed": [
        "impact_boss_prize_mult", "search_weight_future",
    ],
    "boss_used_too_early": [
        "impact_boss_prize_mult", "search_weight_future",
    ],
    "agreement_bad_risk": [
        "impact_retreat_safety", "impact_retreat_penalty", "search_weight_risk",
    ],
    "opponent_return_ko_underestimated": [
        "impact_retreat_safety", "impact_retreat_penalty", "search_weight_risk",
    ],
}

_RISK_FLAG_PARAM_SUGGESTIONS = {
    "no_next_attacker": [
        "impact_crispin_per_energy", "impact_crispin_bolt_bonus",
        "impact_energy_retrieval_per", "impact_attach_bt_req", "search_weight_future",
    ],
    "active_may_be_ko_next_turn": [
        "impact_retreat_safety", "impact_retreat_penalty", "search_weight_risk",
    ],
    "not_enough_energy": [
        "impact_crispin_per_energy", "impact_energy_retrieval_per", "impact_search_item",
        "score_play_pokemon_ogerpon", "impact_attach_bt_req",
    ],
}

# session-scoped override store (cleared on process restart -- by design)
_OVERRIDES = {}


def get_runtime_overrides():
    """Return a copy of the currently staged runtime overrides."""
    return dict(_OVERRIDES)


def validate_param_update(params, key, value):
    """Check whether (key, value) is safe to stage as a runtime override.

    `params` is the base params dict (params.json contents) used only to
    confirm the key is a real, known parameter -- this is what keeps the
    endpoint from accepting arbitrary attacker-supplied keys/values."""
    if not isinstance(key, str) or not key or not _PARAM_NAME_RE.match(key):
        return False, "invalid param name"
    if params is not None and key not in params:
        return False, "unknown param"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, "value must be numeric"
    if not math.isfinite(value):
        return False, "value must be finite"
    return True, None


def set_runtime_override(params, key, value):
    """Stage a session-only override. Never mutates `params` itself."""
    ok, err = validate_param_update(params, key, value)
    if not ok:
        return False, err
    _OVERRIDES[key] = value
    return True, None


def reset_runtime_overrides():
    _OVERRIDES.clear()


def effective_params(params, overrides=None):
    """params.json values with runtime overrides layered on top."""
    merged = dict(params or {})
    merged.update(overrides if overrides is not None else _OVERRIDES)
    return merged


def suggest_params_for_live_review(live_review, available_params=None):
    """Heuristic mapping from a live_review payload to params worth tuning."""
    if not live_review:
        return []
    names = []

    def _add_all(keys):
        for k in keys:
            if k not in names:
                names.append(k)

    _add_all(_CATEGORY_PARAM_SUGGESTIONS.get(live_review.get("category") or "", []))
    for flag in (live_review.get("risk_flags") or []):
        _add_all(_RISK_FLAG_PARAM_SUGGESTIONS.get(flag, []))

    if available_params is not None:
        names = [n for n in names if n in available_params]
    return names


def _shape_candidates(cands):
    try:
        if not cands:
            return {"recommended_action": None, "top_candidates": []}
        ranked = sorted(cands, key=lambda c: c.get("score", 0), reverse=True)
        top = ranked[:5]
        return {"recommended_action": top[0].get("label") if top else None, "top_candidates": top}
    except Exception:
        return {"recommended_action": None, "top_candidates": []}


def build_tuning_preview(compute_fn, params, overrides=None):
    """Compare AI candidates before vs. after applying runtime overrides.

    `compute_fn(effective_params_dict) -> list[{"label","score"}]` is supplied
    by the caller (server.py wraps the real policy.rank() call). Never
    raises -- a broken compute_fn just yields an empty before/after."""
    try:
        before = compute_fn(dict(params or {}))
    except Exception:
        before = None
    try:
        after = compute_fn(effective_params(params, overrides))
    except Exception:
        after = None

    before_shaped = _shape_candidates(before)
    after_shaped = _shape_candidates(after)
    changed = before_shaped["recommended_action"] != after_shaped["recommended_action"]
    return {"before": before_shaped, "after": after_shaped, "changed": changed}


def build_tuning_log_entry(game_id=None, turn=None, live_review=None,
                            param=None, old_value=None, new_value=None,
                            preview=None, review_label="", confidence="", note=""):
    """Assemble one session_tuning_log.jsonl record. Pure function, no I/O."""
    live_review = live_review or {}
    preview = preview or {}
    before = preview.get("before") or {}
    after = preview.get("after") or {}
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "game_id": game_id,
        "turn": turn,
        "category": live_review.get("category"),
        "risk_flags": live_review.get("risk_flags") or [],
        "ai_action_before": before.get("recommended_action"),
        "human_action": live_review.get("human_action"),
        "param": param,
        "old_value": old_value,
        "new_value": new_value,
        "ai_action_after": after.get("recommended_action"),
        "top_candidates_before": before.get("top_candidates") or [],
        "top_candidates_after": after.get("top_candidates") or [],
        "review_label": review_label or "",
        "confidence": confidence or "",
        "note": note or "",
    }


def append_tuning_log(entry, path=None):
    """Append one entry to session_tuning_log.jsonl. Never raises."""
    try:
        target = path or DEFAULT_LOG_PATH
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False
