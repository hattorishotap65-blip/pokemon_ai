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


# === build test entries ===

entries = []

e1 = build_trace_entry(
    deck_name="raging_bolt", turn=2, context="PLAY",
    options=[
        {"i": 0, "label": "▶ Ultra Ball を使う", "score": 900, "type": 7, "cardId": 1121},
        {"i": 1, "label": "▶ Teal Dance を使う", "score": 300, "type": 7, "cardId": 96},
    ],
    ai_pick=[0], human_pick=[1],
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
    deck_name="raging_bolt", turn=3, context="ATTACK",
    options=[
        {"i": 0, "label": "⚔ Bellowing Thunder", "score": 850, "type": 13, "cardId": 63},
        {"i": 1, "label": "⏹ ターン終了", "score": 50, "type": 14},
    ],
    ai_pick=[0], human_pick=[0],
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

# === analyze ===
print("=== basic analysis ===")
summary = analyze(entries)

check("total decisions excludes game_result", summary["total"] == 2)
check("agree=1", summary["agree"] == 1)
check("disagree=1", summary["disagree"] == 1)
check("agree_pct=50", summary["agree_pct"] == 50.0)
check("game_result counted", summary["game_results"].get("loss") == 1)

print("\n=== strategy tag disagree ===")
check("disagree_by_turn_goal", summary["disagree_by_turn_goal"].get("prepare_next_turn_attack") == 1)
check("disagree_by_risk", summary["disagree_by_risk"].get("not_enough_energy") == 1)
check("disagree_by_reason has prioritize", summary["disagree_by_reason"].get("prioritize_energy_acceleration") == 1)
check("disagree_by_reason has build_damage", summary["disagree_by_reason"].get("build_raging_bolt_damage") == 1)
check("disagree_by_win_plan raging_bolt", summary["disagree_by_win_plan"].get("raging_bolt_big_damage_next_turn") == 1)

print("\n=== tag_score_gaps ===")
gaps = summary["tag_score_gaps"]
check("tag gap for prepare_next_turn_attack", "prepare_next_turn_attack" in gaps)
if "prepare_next_turn_attack" in gaps:
    check("avg_gap=600", gaps["prepare_next_turn_attack"]["avg_gap"] == 600.0)
    check("max_gap=600", gaps["prepare_next_turn_attack"]["max_gap"] == 600)
    check("count=1", gaps["prepare_next_turn_attack"]["count"] == 1)

print("\n=== considered summary ===")
cons = summary["considered_summary"]
check("with_considered=2", cons["with_considered"] == 2)
check("human_pick_in_considered=2", cons["human_pick_in_considered"] == 2)
check("ai_pick_in_considered=2", cons["ai_pick_in_considered"] == 2)
check("human_pick_not_considered=0", cons["human_pick_not_considered"] == 0)

print("\n=== improvement_candidates ===")
cands = summary["improvement_candidates"]
check("has candidates", len(cands) > 0)
tags_in_cands = [c["tag"] for c in cands]
check("prepare_next_turn in candidates", "prepare_next_turn_attack" in tags_in_cands)
# No duplicate tags in candidates
tag_kind_pairs = [(c["kind"], c["tag"]) for c in cands]
check("no duplicate candidates", len(tag_kind_pairs) == len(set(tag_kind_pairs)))

print("\n=== format_report ===")
report = format_report(summary)
check("report is string", isinstance(report, str))
check("has Overview", "Overview" in report)
check("has Game Results", "Game Results" in report)
check("has Disagreements by Context", "Disagreements by Context" in report)
check("has Disagreements by Turn Goal", "Disagreements by Turn Goal" in report)
check("has Disagreements by Human Reason", "Disagreements by Human Reason" in report)
check("has Disagreements by Risk", "Disagreements by Risk" in report)
check("has Considered Option Coverage", "Considered Option Coverage" in report)
check("has Improvement Candidates", "Improvement Candidates" in report)
check("has Human chose low-score", "Human chose low-score" in report)
check("has AI recommended", "AI recommended but human ignored" in report)

print("\n=== empty input ===")
empty = analyze([])
check("empty total=0", empty["total"] == 0)
check("empty agree_pct=0", empty["agree_pct"] == 0.0)
check("empty candidates=[]", empty["improvement_candidates"] == [])
check("empty game_results={}", empty["game_results"] == {})

print("\n=== game_result only ===")
result_only = analyze([build_game_result_entry("rb", "drag", "win", 8)])
check("result_only total=0", result_only["total"] == 0)
check("result_only game_results", result_only["game_results"].get("win") == 1)

print("\n=== format_report on empty ===")
empty_report = format_report(empty)
check("empty report is string", isinstance(empty_report, str))
check("empty report has header", "Human Trace Analysis" in empty_report)

print("\n=== all agree ===")
e_agree = build_trace_entry(
    "rb", 1, "PLAY",
    [{"i": 0, "label": "A", "score": 500}],
    ai_pick=[0], human_pick=[0],
)
agree_summary = analyze([e_agree])
check("all_agree: agree=1", agree_summary["agree"] == 1)
check("all_agree: disagree=0", agree_summary["disagree"] == 0)
check("all_agree: agree_pct=100", agree_summary["agree_pct"] == 100.0)
check("all_agree: no candidates", agree_summary["improvement_candidates"] == [])

print("\n=== duplicate tag across turn_goal and reason ===")
e_dup = build_trace_entry(
    "rb", 1, "PLAY",
    [{"i": 0, "label": "A", "score": 100}, {"i": 1, "label": "B", "score": 900}],
    ai_pick=[1], human_pick=[0],
)
e_dup.update({"turn_goal": "take_ko_now", "human_reason_tags": ["take_ko_now"]})
dup_summary = analyze([e_dup])
dup_cands = dup_summary["improvement_candidates"]
dup_tags = [(c["kind"], c["tag"]) for c in dup_cands if c["tag"] == "take_ko_now"]
check("dup tag: no duplicate candidates", len(dup_tags) == len(set(dup_tags)))

print("\n%d checks, %d failures" % (_total, _failures))
if _failures:
    sys.exit(1)
