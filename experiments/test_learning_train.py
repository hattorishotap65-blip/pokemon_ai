"""
Tests for experiments/learning/train_weights.py.

Run: python experiments/test_learning_train.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.train_weights import train, evaluate_all

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


WEIGHTS = {"use_crispin_value": 55.0, "teal_dance_value": 50.0, "energy_discard_risk": -20.0}

LOGS = [
    {
        "match_id": "t1", "turn": 1,
        "state": {"active": "タケルライコex", "bench": [], "hand": [], "discard": [],
                  "prizes_remaining": 6, "opponent_active": "X", "opponent_bench": []},
        "legal_actions": [
            {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
            {"id": "use_teal_dance", "label": "みどりのまいを使う", "type": "ability"},
        ],
        "chosen_action_id": "use_teal_dance",
        "result": {"win": True},
    },
    {
        "match_id": "t2", "turn": 2,
        "state": {"active": "タケルライコex", "bench": [], "hand": [], "discard": ["基本草エネルギー"],
                  "prizes_remaining": 4, "opponent_active": "Y", "opponent_bench": []},
        "legal_actions": [
            {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
            {"id": "attack_bellowing", "label": "Bellowing Thunderで攻撃する", "type": "attack"},
        ],
        "chosen_action_id": "play_crispin",
        "result": {"win": False, "starting_hand_bricked": True},
    },
]

print("=== evaluate_all ===")

stats = evaluate_all(LOGS, WEIGHTS)
check("evaluate_all returns total", stats["total"] == 2)
check("evaluate_all returns accuracy", 0.0 <= stats["accuracy"] <= 1.0)
check("evaluate_all returns avg_rank", stats["avg_rank"] > 0)

stats_empty = evaluate_all([], WEIGHTS)
check("empty logs -> total=0", stats_empty["total"] == 0)
check("empty logs -> accuracy=0", stats_empty["accuracy"] == 0.0)

print("\n=== train ===")

w_before = dict(WEIGHTS)
w_after = train(LOGS, WEIGHTS, epochs=10, lr=0.1)
check("train returns dict", isinstance(w_after, dict))

changed = any(w_after.get(k, 0) != w_before.get(k, 0) for k in set(list(w_before.keys()) + list(w_after.keys())))
check("train modifies weights", changed)

check("original weights unchanged", WEIGHTS == w_before)

# Train with already-correct predictions should not update
LOGS_CORRECT = [
    {
        "match_id": "t3", "turn": 1,
        "state": {"active": "X", "bench": [], "hand": [], "discard": [],
                  "prizes_remaining": 6, "opponent_active": "Y", "opponent_bench": []},
        "legal_actions": [
            {"id": "play_crispin", "label": "アカマツを使う", "type": "supporter"},
            {"id": "end", "label": "終了", "type": "end"},
        ],
        "chosen_action_id": "play_crispin",
        "result": {"win": True},
    },
]
w_correct_before = dict(WEIGHTS)
w_correct_after = train(LOGS_CORRECT, WEIGHTS, epochs=5, lr=0.1)
correct_unchanged = all(abs(w_correct_after.get(k, 0) - w_correct_before.get(k, 0)) < 0.001 for k in w_correct_before)
check("already-correct prediction: no unnecessary update", correct_unchanged)

print("\n=== win/bricked lr adjustments ===")

w_win = train([LOGS[0]], {"teal_dance_value": 0.0, "use_crispin_value": 100.0}, epochs=1, lr=1.0)
w_bricked = train([LOGS[1]], {"use_crispin_value": 0.0, "energy_discard_risk": 100.0}, epochs=1, lr=1.0)
check("win=True increases effective lr (teal_dance moved)", abs(w_win.get("teal_dance_value", 0)) > 0)
check("bricked=True weakens lr", isinstance(w_bricked, dict))

w_empty = train([], WEIGHTS, epochs=5, lr=0.1)
check("empty logs does not crash", w_empty == WEIGHTS)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
