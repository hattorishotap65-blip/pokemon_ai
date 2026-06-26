"""
Tests for experiments/learning/agent_action_adapter.py.

Run: python experiments/test_learning_agent_action_adapter.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.agent_action_adapter import normalize_action, normalize_actions

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


print("=== normalize_action ===")

full = normalize_action({"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"})
check("full candidate preserved", full["id"] == "play_crispin" and full["type"] == "supporter")

no_id = normalize_action({"label": "アカマツを使う"})
check("missing id: generated from label", len(no_id["id"]) > 0)

print("\n=== type inference ===")

check("アカマツ -> supporter", normalize_action({"id": "x", "label": "アカマツを使う"})["type"] == "supporter")
check("crispin -> supporter", normalize_action({"id": "play_crispin", "label": ""})["type"] == "supporter")
check("ハイパーボール -> item", normalize_action({"id": "x", "label": "ハイパーボールを使う"})["type"] == "item")
check("ポケギア -> item", normalize_action({"id": "x", "label": "ポケギア3.0を使う"})["type"] == "item")
check("むしとりセット -> item", normalize_action({"id": "x", "label": "むしとりセットを使う"})["type"] == "item")
check("エネルギー回収 -> item", normalize_action({"id": "x", "label": "エネルギー回収を使う"})["type"] == "item")
check("ボスの指令 -> supporter", normalize_action({"id": "x", "label": "ボスの指令を使う"})["type"] == "supporter")
check("ポケモンキャッチャー -> item", normalize_action({"id": "x", "label": "ポケモンキャッチャーを使う"})["type"] == "item")
check("みどりのまい -> ability", normalize_action({"id": "x", "label": "みどりのまいを使う"})["type"] == "ability")
check("Bellowing Thunder -> attack", normalize_action({"id": "x", "label": "Bellowing Thunderで攻撃する"})["type"] == "attack")
check("エネルギーをつける -> attach", normalize_action({"id": "x", "label": "エネルギーをつける"})["type"] == "attach")
check("ベンチに出す -> play_pokemon", normalize_action({"id": "x", "label": "ベンチに出す"})["type"] == "play_pokemon")
check("ターン終了 -> end", normalize_action({"id": "x", "label": "ターンを終了する"})["type"] == "end")
check("unknown action -> unknown", normalize_action({"id": "x", "label": "something random"})["type"] == "unknown")

print("\n=== edge cases ===")

check("non-dict candidate safe", normalize_action("bad")["type"] == "unknown")
check("empty dict safe", normalize_action({})["type"] == "unknown")

acts = normalize_actions([{"id": "a"}, {"id": "b"}])
check("normalize_actions returns list", len(acts) == 2)

check("normalize_actions with non-list", normalize_actions("bad") == [])

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
