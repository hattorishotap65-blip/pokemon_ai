"""Tests for counterfactual_analyzer."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.human_trace_writer import build_trace_entry, build_game_result_entry
from experiments.web.counterfactual_analyzer import analyze_counterfactual, format_report

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0

def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond: _f += 1

# === empty ===
print("=== empty ===")
r = analyze_counterfactual([])
check("empty: no crash", r["decisions"]["total"] == 0)
check("empty: recommendations list", isinstance(r["recommendations"], list))

# === agree excluded ===
print("\n=== agree excluded ===")
e_agree = build_trace_entry("rb", 1, "MAIN",
    [{"i": 0, "label": "A", "score": 500, "type": 13}],
    ai_pick=[0], human_pick=[0])
r2 = analyze_counterfactual([e_agree])
check("agree: 0 disagrees", r2["decisions"]["main_disagree"] == 0)

# === non-MAIN excluded ===
print("\n=== non-MAIN excluded ===")
e_hand = build_trace_entry("rb", 1, "TO_HAND",
    [{"i": 0, "label": "A", "score": 500, "type": 3},
     {"i": 1, "label": "B", "score": 300, "type": 3}],
    ai_pick=[0], human_pick=[1])
r3 = analyze_counterfactual([e_hand])
check("non-MAIN: 0 disagrees", r3["decisions"]["main_disagree"] == 0)

# === attack_too_early ===
print("\n=== attack_too_early ===")
e_atk = build_trace_entry("rb", 3, "MAIN",
    [{"i": 0, "label": "⚔ Bellowing Thunder", "score": 2000, "type": 13, "cardId": 63},
     {"i": 1, "label": "▶ Crispin を使う", "score": 1300, "type": 7, "cardId": 1198}],
    ai_pick=[0], human_pick=[1],
    my_active={"id": 63, "hp": 200, "maxHp": 240, "energy": 3},
    opp_active={"id": 100, "hp": 320, "maxHp": 320, "energy": 2},
    my_prizes=4, opp_prizes=4)
e_atk.update({"turn_goal": "prepare_next_turn_attack", "agent_goals": ["take_ko_now"],
              "agent_risks": [], "risk_flags": []})
r4 = analyze_counterfactual([e_atk])
check("attack_too_early: classified", r4["categories"].get("attack_too_early", 0) == 1)
check("attack_too_early: human_likely_better", r4["judgments"].get("human_likely_better", 0) == 1)

# === no_next_attacker ===
print("\n=== no_next_attacker ===")
e_nna = build_trace_entry("rb", 5, "MAIN",
    [{"i": 0, "label": "⚔ Bellowing Thunder", "score": 1500, "type": 13},
     {"i": 1, "label": "▶ Raging Bolt ex を使う", "score": 800, "type": 7, "cardId": 63}],
    ai_pick=[0], human_pick=[1],
    my_prizes=3, opp_prizes=3)
e_nna.update({"risk_flags": ["no_next_attacker"], "agent_goals": ["take_ko_now"], "agent_risks": []})
r5 = analyze_counterfactual([e_nna])
check("no_next_attacker: classified", r5["categories"].get("no_next_attacker", 0) == 1)

# === opponent_return_ko_underestimated ===
print("\n=== opponent_return_ko ===")
e_ko = build_trace_entry("rb", 7, "MAIN",
    [{"i": 0, "label": "▶ Ultra Ball を使う", "score": 700, "type": 7},
     {"i": 1, "label": "↩ にげる", "score": 100, "type": 12}],
    ai_pick=[0], human_pick=[1],
    my_active={"id": 63, "hp": 80, "maxHp": 240},
    my_prizes=3, opp_prizes=3)
e_ko.update({"risk_flags": ["active_may_be_ko_next_turn"], "agent_risks": []})
r6 = analyze_counterfactual([e_ko])
check("opp_ko: classified", r6["categories"].get("opponent_return_ko_underestimated", 0) == 1)
check("opp_ko: human_likely_better", r6["judgments"].get("human_likely_better", 0) >= 1)

# === boss_used_too_early ===
print("\n=== boss_used_too_early ===")
e_boss = build_trace_entry("rb", 4, "MAIN",
    [{"i": 0, "label": "▶ Boss's Orders を使う", "score": 1600, "type": 7, "cardId": 1182},
     {"i": 1, "label": "▶ Crispin を使う", "score": 1300, "type": 7, "cardId": 1198}],
    ai_pick=[0], human_pick=[1],
    my_prizes=5, opp_prizes=5)
e_boss.update({"turn_goal": "prepare_next_turn_attack", "agent_goals": [], "agent_risks": []})
r_boss = analyze_counterfactual([e_boss])
check("boss_too_early: classified", r_boss["categories"].get("boss_used_too_early", 0) == 1)
check("boss_too_early: human_likely_better", r_boss["judgments"].get("human_likely_better", 0) == 1)

# === format_report ===
print("\n=== format_report ===")
entries = [e_atk, e_nna, e_ko, build_game_result_entry("rb", "drag", "win", 10)]
r7 = analyze_counterfactual(entries)
report = format_report(r7)
check("report is string", isinstance(report, str))
check("has Counterfactual", "Counterfactual" in report)
check("has Recommendations", "Recommendations" in report or "Categories" in report)
check("has Human Likely Better", "Human Likely Better" in report)

# === combined ===
print("\n=== combined data ===")
check("combined categories", len(r7["categories"]) >= 2)
check("has card_score_gaps", isinstance(r7["card_score_gaps"], dict))
check("has eval_breakdown", isinstance(r7["eval_breakdown_avg"], dict))

print("\n%d/%d passed" % (_t - _f, _t))
if _f: sys.exit(1)
