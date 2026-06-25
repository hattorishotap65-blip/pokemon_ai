"""
Tests for experiments/learning/report.py.

Run: python experiments/test_learning_report.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.report import generate_report

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


LOGS = [
    {
        "match_id": "t1", "turn": 1,
        "deck_archetype": "raging_bolt_ogerpon",
        "opponent_archetype": "lucario_ex",
        "state": {"active": "X", "bench": [], "hand": [], "discard": [],
                  "prizes_remaining": 6, "opponent_active": "Y", "opponent_bench": []},
        "legal_actions": [
            {"id": "a1", "label": "action1", "type": "item"},
            {"id": "a2", "label": "action2", "type": "attack"},
        ],
        "chosen_action_id": "a1",
        "result": {"win": True},
    },
    {
        "match_id": "t2", "turn": 2,
        "deck_archetype": "raging_bolt_ogerpon",
        "opponent_archetype": "dragapult_ex",
        "state": {"active": "X", "bench": [], "hand": [], "discard": [],
                  "prizes_remaining": 4, "opponent_active": "Z", "opponent_bench": []},
        "legal_actions": [
            {"id": "a3", "label": "action3", "type": "supporter"},
            {"id": "a4", "label": "action4", "type": "ability"},
        ],
        "chosen_action_id": "a3",
        "result": {"win": False},
    },
]

W_BEFORE = {"take_ko_value": 100.0, "use_crispin_value": 55.0}
W_AFTER = {"take_ko_value": 90.0, "use_crispin_value": 65.0, "new_weight": 5.0}

STATS_BEFORE = {"total": 2, "matches": 1, "accuracy": 0.5, "avg_rank": 1.5}
STATS_AFTER = {"total": 2, "matches": 2, "accuracy": 1.0, "avg_rank": 1.0}

print("=== generate_report ===")

report = generate_report(LOGS, W_BEFORE, W_AFTER, STATS_BEFORE, STATS_AFTER)

check("returns string", isinstance(report, str))
check("contains Summary", "Summary" in report)
check("contains Accuracy before", "50.0%" in report)
check("contains Accuracy after", "100.0%" in report)
check("contains Increased Weights", "Increased" in report)
check("contains Decreased Weights", "Decreased" in report)
check("contains use_crispin_value increase", "use_crispin_value" in report and "+10.00" in report)
check("contains take_ko_value decrease", "take_ko_value" in report and "-10.00" in report)
check("contains By Deck Archetype", "Deck Archetype" in report)
check("contains By Opponent Archetype", "Opponent Archetype" in report)
check("contains lucario_ex", "lucario_ex" in report)
check("contains dragapult_ex", "dragapult_ex" in report)

print("\n=== result breakdown ===")

check("contains Result Breakdown", "Result Breakdown" in report)
check("contains Win entries", "Win entries" in report)
check("contains Loss entries", "Loss entries" in report)
check("contains Bricked entries", "Bricked entries" in report)
check("contains Average prizes taken", "Average prizes taken" in report)
check("contains Average turns to win", "Average turns to win" in report)

print("\n=== empty logs ===")

report_empty = generate_report([], W_BEFORE, W_AFTER,
                               {"total": 0, "matches": 0, "accuracy": 0.0, "avg_rank": 0.0},
                               {"total": 0, "matches": 0, "accuracy": 0.0, "avg_rank": 0.0})
check("empty logs does not crash", isinstance(report_empty, str))
check("empty logs contains Summary", "Summary" in report_empty)
check("empty logs Result Breakdown safe", "Result Breakdown" in report_empty)

print("\n=== no weight changes ===")

report_same = generate_report(LOGS, W_BEFORE, W_BEFORE, STATS_BEFORE, STATS_BEFORE)
check("identical weights: no crash", isinstance(report_same, str))
check("identical weights: unchanged count shown", "Unchanged weights:" in report_same)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
