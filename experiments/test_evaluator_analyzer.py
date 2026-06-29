"""Tests for evaluator_analyzer."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.human_trace_writer import build_trace_entry, build_game_result_entry
from experiments.web.evaluator_analyzer import analyze_evaluator, format_report

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0

def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond: _f += 1

entries = []

e1 = build_trace_entry("rb", 3, "MAIN",
    [{"i": 0, "label": "▶ Crispin を使う", "score": 1300, "type": 7, "cardId": 1198},
     {"i": 1, "label": "⚔ ワザ Bellowing Thunder", "score": 2000, "type": 13, "cardId": 63}],
    ai_pick=[1], human_pick=[0],
    opp_active={"id": 100, "name": "Dragapult ex", "hp": 320, "maxHp": 320, "energy": 2, "ex": True},
    my_active={"id": 63, "name": "Raging Bolt ex", "hp": 100, "maxHp": 240, "energy": 2},
    my_prizes=4, opp_prizes=4)
e1.update({"turn_goal": "take_ko_now", "risk_flags": ["active_may_be_ko_next_turn"],
           "agent_goals": ["take_ko_now"], "agent_risks": []})
entries.append(e1)

e2 = build_trace_entry("rb", 5, "MAIN",
    [{"i": 0, "label": "▶ Teal Mask Ogerpon ex を使う", "score": 870, "type": 7},
     {"i": 1, "label": "⚔ ワザ Bellowing Thunder", "score": 1500, "type": 13}],
    ai_pick=[1], human_pick=[0],
    my_prizes=3, opp_prizes=4)
e2.update({"turn_goal": "setup_board", "agent_goals": ["take_ko_now"], "agent_risks": []})
entries.append(e2)

e3 = build_trace_entry("rb", 7, "MAIN",
    [{"i": 0, "label": "⚔ ワザ Bellowing Thunder", "score": 2000, "type": 13},
     {"i": 1, "label": "⏹ ターン終了", "score": 50, "type": 14}],
    ai_pick=[0], human_pick=[0])
entries.append(e3)

entries.append(build_game_result_entry("rb", "dragapult", "win", 9))

print("=== analyze_evaluator ===")
result = analyze_evaluator(entries)
check("has games", result["games"]["wins"] == 1)
check("has decisions", result["decisions"]["total"] == 3)
check("has action_type_gap", "ATTACK" in result["action_type_gap"])
check("ATTACK gap negative", result["action_type_gap"]["ATTACK"]["diff"] < 0)
check("has eval_signals", isinstance(result["eval_signals"], dict))
check("has impact_candidates", isinstance(result["impact_candidates"], dict))
check("has opponent_model_gaps", "active_ko_missed" in result["opponent_model_gaps"])
check("active_ko_missed=1", result["opponent_model_gaps"]["active_ko_missed"] == 1)
check("has recommendations", len(result["recommendations"]) > 0)

print("\n=== format_report ===")
report = format_report(result)
check("report is string", isinstance(report, str))
check("has header", "Evaluator Analysis" in report)
check("has recommendations section", "Recommendations" in report)

print("\n=== empty input ===")
empty = analyze_evaluator([])
check("empty has games", empty["games"]["total"] == 0)
check("empty has recommendations", isinstance(empty["recommendations"], list))

print("\n%d/%d passed" % (_t - _f, _t))
if _f: sys.exit(1)
