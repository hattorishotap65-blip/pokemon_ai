"""
Extract feature vectors from candidate actions.

Each action + state -> dict[str, float] of features.
Features are named to match weight keys in params JSON.
"""
from __future__ import annotations
from typing import Dict


def extract_action_features(action: dict, state: dict, all_actions: list) -> Dict[str, float]:
    """Extract feature vector for a single candidate action."""
    features: Dict[str, float] = {}
    atype = action.get("type", "")
    aid = action.get("id", "")
    label = action.get("label", "")

    active = state.get("active", "")
    bench = state.get("bench") or []
    hand = state.get("hand") or []
    discard = state.get("discard") or []
    prizes = state.get("prizes_remaining", 6)
    opp_active = state.get("opponent_active", "")
    opp_bench = state.get("opponent_bench") or []

    has_attack = any(a.get("type") == "attack" for a in all_actions)
    bench_count = len(bench)
    hand_count = len(hand)

    # --- Attack features ---
    if atype == "attack":
        features["take_ko_value"] = 1.0 if "ko" in label.lower() else 0.0
        features["take_two_prizes_value"] = 1.0 if "ex" in opp_active.lower() else 0.0
        features["ko_main_attacker_value"] = 1.0 if any(
            kw in opp_active.lower() for kw in ("lucario", "bolt", "dragapult", "crustle")
        ) else 0.0
        features["energy_discard_risk"] = 1.0 if "discard" in label.lower() or "bellowing" in aid.lower() else 0.0
        features["next_turn_attack_continuity"] = 1.0 if len(discard) >= 2 else 0.0

    # --- Setup features ---
    if atype == "ability":
        features["teal_dance_value"] = 1.0 if "teal" in aid.lower() or "dance" in label.lower() else 0.0
        features["bench_ogerpon_value"] = 0.0

    if atype in ("item", "supporter", "trainer"):
        if "crispin" in aid.lower() or "アカマツ" in label:
            features["use_crispin_value"] = 1.0
        if "ultra_ball" in aid.lower() or "ハイパーボール" in label:
            features["use_ultra_ball_setup_value"] = 1.0 if bench_count < 3 else 0.3
        if "pokegear" in aid.lower() or "ポケギア" in label:
            features["dig_deck_value"] = 1.0
        if "energy_retrieval" in aid.lower() or "エネルギー回収" in label:
            features["preserve_energy_retrieval_value"] = 1.0 if len(discard) >= 2 else 0.3
        if "boss" in aid.lower() or "ボス" in label:
            features["preserve_boss_value"] = 1.0 if prizes <= 2 else 0.3
        if "catcher" in aid.lower() or "キャッチャー" in label:
            features["use_catcher_value"] = 0.5
        if "unfair" in aid.lower() or "アンフェア" in label:
            features["block_opponent_win_value"] = 1.0 if prizes > state.get("opponent_prizes", 6) else 0.3
        if "tera_orb" in aid.lower() or "テラスタル" in label:
            has_ogerpon = any("オーガポン" in b for b in bench) or "オーガポン" in active
            features["use_ultra_ball_setup_value"] = 0.0 if has_ogerpon else 0.8
        if "bug_catching" in aid.lower() or "むしとり" in label:
            features["dig_deck_value"] = 0.8

    if atype == "play_pokemon":
        if "オーガポン" in label or "ogerpon" in aid.lower():
            features["bench_ogerpon_value"] = 1.0
        if "ライコ" in label or "raging" in aid.lower():
            features["prepare_second_raging_bolt_value"] = 1.0 if "ライコ" in active or "Raging" in active else 0.0

    if atype == "attach":
        features["next_turn_attack_continuity"] = 0.5

    # --- Prize race features ---
    if prizes <= 2:
        features["setup_next_turn_win_value"] = 1.0 if atype == "attack" and features.get("take_ko_value", 0) > 0 else 0.0
    opp_prizes = state.get("opponent_prizes", 6)
    if opp_prizes <= 2:
        features["block_opponent_win_value"] = max(features.get("block_opponent_win_value", 0.0), 0.5)

    return features
