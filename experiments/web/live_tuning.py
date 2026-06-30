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
        "impact_play_bolt", "score_play_pokemon_raging_bolt",
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
        "impact_play_bolt", "score_play_pokemon_raging_bolt",
    ],
    "active_may_be_ko_next_turn": [
        "impact_retreat_safety", "impact_retreat_penalty", "search_weight_risk",
    ],
    "not_enough_energy": [
        "impact_crispin_per_energy", "impact_energy_retrieval_per", "impact_search_item",
        "score_play_pokemon_ogerpon", "impact_attach_bt_req",
    ],
}

# Human-readable description of what each suggestable param actually controls
# in raging_bolt/main.py, shown in the Live Tuning Panel so a reviewer doesn't
# have to read the agent source to know what a number does.
PARAM_DESCRIPTIONS = {
    "impact_crispin_per_energy":
        "Crispinを使う行動の先読みスコアへの加点。トラッシュにあるエネルギー枚数"
        "(最大3枚分)に比例する。値を上げるほどトラッシュエネルギーが多いときに"
        "Crispinを優先しやすくなる。",
    "impact_crispin_bolt_bonus":
        "タケルライコexがまだ攻撃準備できていない時、Crispinの先読みスコアに"
        "上乗せされる固定ボーナス。値を上げるほど『タケルライコ未準備ならCrispin'"
        "を優先』という傾向が強まる。",
    "impact_energy_retrieval_per":
        "エネルギーリトリーバルを使う行動の先読みスコアへの加点。トラッシュの"
        "エネルギー枚数(最大2枚分)に比例する。",
    "impact_attach_bt_req":
        "Bellowing Thunder(タケルライコの技)に必要なエネルギーをタケルライコへ"
        "貼る行動への先読みスコア加点。値を上げるほどタケルライコへのエネルギー"
        "加速を優先しやすくなる。",
    "search_weight_future":
        "AIの最終スコア = 即時スコア×search_weight_immediate + 先読み(future_delta)"
        "×search_weight_future + リスク×search_weight_risk のうち、先読み(将来の"
        "展開価値)をどれだけ重視するかの重み。上げるほど目先の即時スコアより"
        "将来の展開を優先するようになる。",
    "impact_boss_prize_mult":
        "ボスの指令を使う行動の先読みスコアへの加点。狙えるKO対象のサイド残り"
        "枚数に比例する。",
    "impact_retreat_safety":
        "にげる行動が、次の相手ターンでバトル場が倒されるリスクを回避できる"
        "場面で加点される量。",
    "impact_retreat_penalty":
        "にげる行動そのものに対する基本ペナルティ(にげるコストの損失分、通常は"
        "負の値)。",
    "search_weight_risk":
        "AIの最終スコアのうち、相手の返り討ち(次ターンKOされる)リスクをどれだけ"
        "重視するかの重み。上げるほどリスク回避を優先するようになる。",
    "impact_search_item":
        "Ultra Ball/Bug Catching Set/Tera Orbなどのサーチアイテムを使う行動への"
        "先読みスコア加点。",
    "score_play_pokemon_ogerpon":
        "オーガポンexを場に出す行動の基礎スコア(rank()段階の即時評価値。先読み"
        "重みsearch_weight_immediateで効くため影響が大きい)。",
    "impact_play_bolt":
        "タケルライコexを場に出す(ベンチに展開する)行動の先読みスコアへの固定"
        "加点。値を上げるほど、他の行動(Crispinなど)よりタケルライコexを先に"
        "出すことを優先しやすくなる。",
    "score_play_pokemon_raging_bolt":
        "タケルライコexを場に出す行動の基礎スコア(rank()段階の即時評価値)。"
        "search_weight_immediateで効くため、先読みスコアより比重が大きくなる"
        "場面もある。",
}


def describe_param(name):
    """Human-readable description of what `name` controls, for the tuning UI."""
    return PARAM_DESCRIPTIONS.get(name, "")

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


def _empty_score_snapshot():
    return {"target_score": None, "top_label": None, "top_score": None, "gap": None}


def _score_snapshot(compute_fn, params, param_name, value, target_label):
    """One (param_name=value) probe: target_label's score, the current top
    candidate's label/score, and the gap between them. Returns the "empty"
    shape (all None) if compute_fn fails or target_label isn't a candidate
    at this value -- never raises."""
    eff = dict(params)
    eff[param_name] = value
    try:
        cands = compute_fn(eff)
    except Exception:
        cands = None
    if not cands:
        return _empty_score_snapshot()
    by_label = {}
    try:
        for c in cands:
            lbl = c.get("label")
            sc = c.get("score", 0)
            if lbl not in by_label or sc > by_label[lbl]:
                by_label[lbl] = sc
    except Exception:
        return _empty_score_snapshot()
    if target_label not in by_label or not by_label:
        return _empty_score_snapshot()
    top_label = max(by_label, key=by_label.get)
    return {"target_score": by_label[target_label], "top_label": top_label,
            "top_score": by_label[top_label], "gap": by_label[target_label] - by_label[top_label]}


def find_param_value_for_target(compute_fn, params, param_name, target_label,
                                 max_iter=20, max_abs_value=1_000_000.0):
    """Search for a value of params[param_name] that makes target_label the
    top-scoring candidate out of compute_fn(effective_params_dict).

    This answers "what should I change this param to, to get the AI to pick
    what I picked instead?" -- it's a heuristic example search (geometric
    step in both directions from the current value), not an exact solver,
    since score-vs-param isn't guaranteed monotonic for every param (e.g.
    the search_weight_* family affects every candidate's score, not just
    target_label's). Searches the *full* candidate list compute_fn returns,
    not just a top-N slice, since target_label may not start out near the
    top (that's often why it's a disagreement in the first place).

    Returns a dict, never raises:
        found              -- True if some tried value made target_label's
                               score >= every other candidate's (ties count)
        value              -- the value to try (the winning value if found,
                               else the best-gap value seen, else None if
                               target_label never appeared as a candidate)
        before_value       -- params[param_name]'s value at search start
        before_gap         -- target_label's score minus the top score, at
                               before_value (None if not found there)
        after_gap          -- same gap, but at `value`
        before_target_score / before_top_label / before_top_score
                           -- the actual priority-score numbers at
                              before_value, so the panel can show e.g.
                              "あなたの手: 2500 / AI推奨(Crispin): 3200"
        after_target_score / after_top_label / after_top_score
                           -- the same numbers at `value`, e.g. after the
                              suggested change "あなたの手: 3200 / AI推奨:
                              あなたの手 3200" once found=True
    """
    base_value = params.get(param_name, 0) or 0

    def _snap(value):
        return _score_snapshot(compute_fn, params, param_name, value, target_label)

    def _result(found, value, after):
        before = _snap(base_value)
        return {
            "found": found, "value": value, "before_value": base_value,
            "before_gap": before["gap"], "after_gap": after["gap"],
            "before_target_score": before["target_score"], "before_top_label": before["top_label"],
            "before_top_score": before["top_score"],
            "after_target_score": after["target_score"], "after_top_label": after["top_label"],
            "after_top_score": after["top_score"],
        }

    before = _snap(base_value)
    if before["gap"] is not None and before["gap"] >= 0:
        return _result(True, base_value, before)

    best_value, best = base_value, before
    for direction in (1, -1):
        step = max(abs(base_value) * 0.5, 0.05)
        value = base_value
        for _ in range(max_iter):
            value = value + direction * step
            if abs(value) > max_abs_value:
                break
            cur = _snap(value)
            if cur["gap"] is None:
                step *= 1.6
                continue
            if best["gap"] is None or cur["gap"] > best["gap"]:
                best, best_value = cur, value
            if cur["gap"] >= 0:
                return _result(True, round(value, 4), cur)
            step *= 1.6

    return _result(False, (round(best_value, 4) if best["gap"] is not None else None), best)


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
