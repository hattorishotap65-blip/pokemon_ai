"""
Tests for experiments/learning/evaluator.py.

Run: python experiments/test_learning_evaluator.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.evaluator import score_action, rank_actions, evaluate_log_entry

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
    "hand": ["アカマツ"],
    "discard": [],
    "prizes_remaining": 6,
    "opponent_active": "ドラパルトex",
    "opponent_bench": [],
}

ACTIONS = [
    {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
    {"id": "use_teal_dance", "label": "みどりのまいを使う", "type": "ability"},
    {"id": "attack_bellowing", "label": "Bellowing Thunderで攻撃する", "type": "attack"},
]

WEIGHTS = {"use_crispin_value": 55.0, "teal_dance_value": 50.0, "energy_discard_risk": -20.0}

print("=== score_action ===")

s = score_action(ACTIONS[0], STATE, ACTIONS, WEIGHTS)
check("crispin scores positive", s > 0)

s_empty = score_action(ACTIONS[0], STATE, ACTIONS, {})
check("undefined weights treated as 0", s_empty == 0.0)

print("\n=== rank_actions ===")

ranked = rank_actions(ACTIONS, STATE, WEIGHTS)
check("rank_actions returns list of tuples", len(ranked) == 3 and isinstance(ranked[0], tuple))
check("rank_actions is score descending", ranked[0][1] >= ranked[1][1] >= ranked[2][1])
check("crispin ranks first with these weights", ranked[0][0] == "play_crispin")

ranked_empty = rank_actions([], STATE, WEIGHTS)
check("empty actions returns empty list", ranked_empty == [])

print("\n=== evaluate_log_entry ===")

entry = {
    "legal_actions": ACTIONS,
    "state": STATE,
    "chosen_action_id": "play_crispin",
}
result = evaluate_log_entry(entry, WEIGHTS)
check("evaluate_log_entry returns match=True when chosen is top", result["match"] is True)
check("evaluate_log_entry rank is 1", result["rank"] == 1)

entry_miss = {
    "legal_actions": ACTIONS,
    "state": STATE,
    "chosen_action_id": "attack_bellowing",
}
result_miss = evaluate_log_entry(entry_miss, WEIGHTS)
check("evaluate_log_entry match=False when chosen is not top", result_miss["match"] is False)
check("evaluate_log_entry rank > 1", result_miss["rank"] > 1)

entry_no_chosen = {
    "legal_actions": ACTIONS,
    "state": STATE,
    "chosen_action_id": "",
}
result_nc = evaluate_log_entry(entry_no_chosen, WEIGHTS)
check("no chosen_action_id -> rank=-1", result_nc["rank"] == -1)

entry_empty = {
    "legal_actions": [],
    "state": STATE,
    "chosen_action_id": "x",
}
result_empty = evaluate_log_entry(entry_empty, WEIGHTS)
check("empty legal_actions does not crash", result_empty["rank"] == -1)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
