"""
Normalize runtime candidate actions into learning evaluator format.

Converts varied action representations into the standard
{id, label, type} format that action_features.py expects.
"""
from __future__ import annotations
from typing import Dict, List, Optional

_TYPE_KEYWORDS = {
    "supporter": [
        "アカマツ", "crispin", "リーリエ", "lillie", "ボスの指令", "boss",
        "supporter",
    ],
    "item": [
        "ハイパーボール", "ultra_ball", "ポケギア", "pokegear",
        "むしとりセット", "bug_catching", "エネルギー回収", "energy_retrieval",
        "ポケモンキャッチャー", "catcher", "テラスタルオーブ", "tera_orb",
        "アンフェアスタンプ", "unfair", "item",
    ],
    "ability": [
        "みどりのまい", "teal_dance", "teal dance", "ability",
    ],
    "attack": [
        "bellowing", "burst roar", "攻撃", "attack",
    ],
    "attach": [
        "エネルギーをつける", "エネルギーを付ける", "attach",
    ],
    "play_pokemon": [
        "ベンチに出す", "場に出す", "play_pokemon",
    ],
    "end": [
        "ターン終了", "ターンを終了", "end_turn", "end",
    ],
}


def _infer_type(action_id: str, label: str) -> str:
    """Infer action type from id and label text."""
    search = (action_id + " " + label).lower()
    for atype, keywords in _TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in search:
                return atype
    return "unknown"


def _make_id(candidate: dict) -> str:
    """Generate an action id from available fields."""
    for key in ("id", "action_id", "name"):
        val = candidate.get(key)
        if val:
            return str(val)
    label = candidate.get("label", "")
    if label:
        return label.replace(" ", "_")[:40]
    return "action_%d" % id(candidate)


def normalize_action(candidate: dict) -> dict:
    """Normalize a single candidate action into learning format."""
    if not isinstance(candidate, dict):
        return {"id": "invalid", "label": "", "type": "unknown"}

    action_id = str(candidate.get("id") or _make_id(candidate))
    label = str(candidate.get("label") or candidate.get("name") or action_id)
    atype = candidate.get("type", "")
    if not atype or atype not in (
        "attack", "ability", "item", "supporter", "trainer",
        "attach", "play_pokemon", "end", "unknown",
    ):
        atype = _infer_type(action_id, label)

    return {"id": action_id, "label": label, "type": atype}


def normalize_actions(candidates: list) -> list:
    """Normalize a list of candidate actions."""
    if not isinstance(candidates, list):
        return []
    return [normalize_action(c) for c in candidates]
