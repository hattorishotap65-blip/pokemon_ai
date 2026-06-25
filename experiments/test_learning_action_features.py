"""
Tests for experiments/learning/action_features.py.

Run: python experiments/test_learning_action_features.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.action_features import extract_action_features

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0
_total = 0


def check(label, condition):
    global _failures, _total
    _total += 1
    status = PASS if condition else FAIL
    print("  %s  %s" % (status, label))
    if not condition:
        _failures += 1


STATE = {
    "active": "タケルライコex",
    "bench": ["オーガポンみどりのめんex"],
    "hand": ["アカマツ", "ハイパーボール", "基本草エネルギー"],
    "discard": ["基本草エネルギー"],
    "prizes_remaining": 6,
    "opponent_active": "ドラパルトex",
    "opponent_bench": [],
    "opponent_prizes": 6,
}

ACTIONS = [
    {"id": "play_ogerpon", "label": "オーガポンみどりのめんexをベンチに出す", "type": "play_pokemon"},
    {"id": "use_teal_dance", "label": "みどりのまいを使う", "type": "ability"},
    {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
    {"id": "play_ultra_ball", "label": "ハイパーボールを使う", "type": "item"},
    {"id": "play_pokegear", "label": "ポケギア3.0を使う", "type": "item"},
    {"id": "play_bug_catching", "label": "むしとりセットを使う", "type": "item"},
    {"id": "play_energy_retrieval", "label": "エネルギー回収を使う", "type": "item"},
    {"id": "play_boss", "label": "ボスの指令を使う", "type": "supporter"},
    {"id": "play_catcher", "label": "ポケモンキャッチャーを使う", "type": "item"},
    {"id": "play_unfair_stamp", "label": "アンフェアスタンプを使う", "type": "item"},
    {"id": "attack_bellowing_thunder", "label": "Bellowing Thunderで攻撃する", "type": "attack"},
]

print("=== action feature extraction ===")

f = extract_action_features(ACTIONS[0], STATE, ACTIONS)
check("play_ogerpon -> bench_ogerpon_value", f.get("bench_ogerpon_value", 0) > 0)

f = extract_action_features(ACTIONS[1], STATE, ACTIONS)
check("teal_dance -> teal_dance_value", f.get("teal_dance_value", 0) > 0)

f = extract_action_features(ACTIONS[2], STATE, ACTIONS)
check("crispin -> use_crispin_value", f.get("use_crispin_value", 0) > 0)

f = extract_action_features(ACTIONS[3], STATE, ACTIONS)
check("ultra_ball -> use_ultra_ball_setup_value", f.get("use_ultra_ball_setup_value", 0) > 0)

f = extract_action_features(ACTIONS[4], STATE, ACTIONS)
check("pokegear -> dig_deck_value", f.get("dig_deck_value", 0) > 0)

f = extract_action_features(ACTIONS[5], STATE, ACTIONS)
check("bug_catching -> dig_deck_value", f.get("dig_deck_value", 0) > 0)

f = extract_action_features(ACTIONS[6], STATE, ACTIONS)
check("energy_retrieval -> preserve_energy_retrieval_value", f.get("preserve_energy_retrieval_value", 0) > 0)

f = extract_action_features(ACTIONS[7], STATE, ACTIONS)
check("boss -> preserve_boss_value", f.get("preserve_boss_value", 0) > 0)

f = extract_action_features(ACTIONS[8], STATE, ACTIONS)
check("catcher -> use_catcher_value", f.get("use_catcher_value", 0) > 0)

f = extract_action_features(ACTIONS[9], STATE, ACTIONS)
check("unfair_stamp -> block_opponent_win_value", f.get("block_opponent_win_value", 0) > 0)

f = extract_action_features(ACTIONS[10], STATE, ACTIONS)
check("bellowing_thunder -> energy_discard_risk", f.get("energy_discard_risk", 0) > 0)

print("\n=== empty/minimal state ===")

f = extract_action_features({"id": "x", "type": "item"}, {}, [])
check("empty state does not crash", isinstance(f, dict))

f = extract_action_features({"id": "y", "type": "attack"}, {"active": ""}, [])
check("minimal attack does not crash", isinstance(f, dict))

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
