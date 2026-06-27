"""Tests for strategy-tag aware human trace analysis."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.human_trace_writer import build_trace_entry, build_game_result_entry
from experiments.web.human_trace_analyzer import analyze, format_report

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


entries = []

e1 = build_trace_entry(
    deck_name="raging_bolt",
    turn=2,
    context="PLAY",
    options=[
        {"i": 0, "label": "▶ Ultra Ball を使う", "score": 900, "type": 7, "cardId": 1121},
        {"i": 1, "label": "▶ Teal Dance を使う", "score": 300, "type": 7, "cardId": 96},
    ],
    ai_pick=[0],
    human_pick=[1],
)
e1.update({
    "turn_goal": "prepare_next_turn_attack",
    "win_plan_tags": ["raging_bolt_big_damage_next_turn", "ogerpon_energy_engine"],
    "risk_flags": ["not_enough_energy"],
    "human_reason_tags": ["prioritize_energy_acceleration", "build_raging_bolt_damage"],
    "human_considered": [0, 1],
})
entries.append(e1)

e2 = build_trace_entry(
    deck_name="raging_bolt",
    turn=3,
    context="ATTACK",
    options=[
        {"i": 0, "label": "⚔ Bellowing Thunder", "score": 850, "type": 13, "cardId": 63},
        {"i": 1, "label": "⏹ ターン終了", "score": 50, "type": 14},
    ],
    ai_pick=[0],
    human_pick=[0],
)
e2.update({
    "turn_goal": "take_ko_now",
    "win_plan_tags": ["ko_active"],
    "risk_flags": [],
    "human_reason_tags": ["take_ko_now"],
    "human_considered": [0],
})
entries.append(e2)
entries.append(build_game_result_entry("raging_bolt", "dragapult", "loss", 9))

summary = analyze(entries)

check("total decisions excludes result", summary["total"] == 2)
check("agreement pct", summary["agree_pct"] == 50.0)
check("result counted", summary["game_results"]["loss"] == 1)
check("disagree by turn goal", summary["disagree_by_turn_goal"]["prepare_next_turn_attack"] == 1)
check("disagree by risk", summary["disagree_by_risk"]["not_enough_energy"] == 1)
check("disagree by reason", summary["disagree_by_reason"]["prioritize_energy_acceleration"] == 1)
check("tag score gap", summary["tag_score_gaps"]["prepare_next_turn_attack"]["avg_gap"] == 600.0)
check("considered count", summary["considered_summary"]["with_considered"] == 2)
check("human considered", summary["considered_summary"]["human_pick_in_considered"] == 2)
check("ai considered", summary["considered_summary"]["ai_pick_in_considered"] == 2)
check("has improvement candidates", len(summary["improvement_candidates"]) > 0)

report = format_report(summary)
check("report includes improvement section", "Improvement Candidates" in report)
check("report includes strategy tag", "prepare_next_turn_attack" in report)

print("\n%d checks, %d failures" % (_total, _failures))
if _failures:
    sys.exit(1)
