"""Tests for human trace writer, analyzer, and params recommender."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.human_trace_writer import (
    build_trace_entry, write_trace_entry, load_traces, trace_path,
    build_game_result_entry,
)
from experiments.web.human_trace_analyzer import analyze, format_report
from experiments.web.params_recommender import recommend

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


# === trace_writer ===
print("=== build_trace_entry ===")

entry = build_trace_entry(
    deck_name="raging_bolt",
    turn=3,
    context="PLAY",
    options=[
        {"i": 0, "label": "⚔ ワザ Bellowing Thunder (0)", "score": 900, "type": 13, "cardId": 63, "attackId": 72},
        {"i": 1, "label": "⏹ ターン終了", "score": 50, "type": 14, "cardId": None, "attackId": None},
    ],
    ai_pick=[0],
    human_pick=[0],
    params_path="params.json",
    opp_deck="dragapult",
    opp_active={"id": 100, "name": "Dragapult", "hp": 150, "maxHp": 320, "energy": 2},
    my_active={"id": 63, "name": "Raging Bolt ex", "hp": 240, "maxHp": 240, "energy": 3},
    my_prizes=5,
    opp_prizes=4,
)

check("entry has ts", "ts" in entry and isinstance(entry["ts"], float))
check("entry has deck", entry["deck"] == "raging_bolt")
check("entry has opp_deck", entry["opp_deck"] == "dragapult")
check("entry has turn", entry["turn"] == 3)
check("entry has context", entry["context"] == "PLAY")
check("entry has options", len(entry["options"]) == 2)
check("entry has ai_pick", entry["ai_pick"] == [0])
check("entry has human_pick", entry["human_pick"] == [0])
check("entry agree=True", entry["agree"] is True)
check("entry has opp_active", entry["opp_active"]["name"] == "Dragapult")
check("entry has my_active", entry["my_active"]["id"] == 63)
check("entry has my_prizes", entry["my_prizes"] == 5)
check("entry has opp_prizes", entry["opp_prizes"] == 4)

entry_disagree = build_trace_entry(
    deck_name="raging_bolt", turn=5, context="ATTACH",
    options=[
        {"i": 0, "label": "🔋 エネルギーをつける → Ogerpon", "score": 700, "type": 8, "cardId": 96, "attackId": None},
        {"i": 1, "label": "🔋 エネルギーをつける → Raging Bolt", "score": 600, "type": 8, "cardId": 63, "attackId": None},
    ],
    ai_pick=[0], human_pick=[1],
    opp_deck="megastarmie",
)
check("disagree entry agree=False", entry_disagree["agree"] is False)
check("disagree has opp_deck", entry_disagree["opp_deck"] == "megastarmie")

print("\n=== build_game_result_entry ===")
result_entry = build_game_result_entry("raging_bolt", "dragapult", "win", 12)
check("result has type", result_entry["type"] == "game_result")
check("result has deck", result_entry["deck"] == "raging_bolt")
check("result has opp_deck", result_entry["opp_deck"] == "dragapult")
check("result has result", result_entry["result"] == "win")
check("result has turns", result_entry["turns"] == 12)

print("\n=== write/load traces ===")
tmp = tempfile.mkdtemp()
tp = os.path.join(tmp, "test_trace.jsonl")
write_trace_entry(tp, entry)
write_trace_entry(tp, entry_disagree)
check("trace file created", os.path.exists(tp))

loaded = load_traces(tp)
check("loaded 2 entries", len(loaded) == 2)
check("first entry deck", loaded[0]["deck"] == "raging_bolt")
check("second entry turn", loaded[1]["turn"] == 5)

print("\n=== load empty/missing ===")
check("missing file -> empty", load_traces("/nonexistent.jsonl") == [])

print("\n=== trace_path ===")
tp2 = trace_path("test_session")
check("trace_path contains session id", "test_session" in tp2)
check("trace_path ends with .jsonl", tp2.endswith(".jsonl"))

# === analyzer ===
print("\n=== analyze ===")

entries = [
    build_trace_entry("rb", 1, "PLAY", [
        {"i": 0, "label": "▶ Raging Bolt ex を使う", "score": 500, "type": 7, "cardId": 63},
        {"i": 1, "label": "▶ Teal Mask Ogerpon ex を使う", "score": 600, "type": 7, "cardId": 96},
    ], ai_pick=[1], human_pick=[1]),
    build_trace_entry("rb", 2, "PLAY", [
        {"i": 0, "label": "▶ Crispin を使う", "score": 700, "type": 7, "cardId": 1198},
        {"i": 1, "label": "▶ Lillie's Determination を使う", "score": 600, "type": 7, "cardId": 1227},
    ], ai_pick=[0], human_pick=[1]),
    build_trace_entry("rb", 3, "ATTACK", [
        {"i": 0, "label": "⚔ ワザ Bellowing Thunder (0)", "score": 900, "type": 13, "cardId": 63, "attackId": 72},
        {"i": 1, "label": "⏹ ターン終了", "score": 50, "type": 14},
    ], ai_pick=[0], human_pick=[0]),
    build_trace_entry("rb", 4, "PLAY", [
        {"i": 0, "label": "▶ Boss's Orders を使う", "score": 900, "type": 7, "cardId": 1182},
        {"i": 1, "label": "▶ Ultra Ball を使う", "score": 500, "type": 7, "cardId": 1121},
    ], ai_pick=[0], human_pick=[1]),
]

summary = analyze(entries)
check("total=4", summary["total"] == 4)
check("agree=2", summary["agree"] == 2)
check("disagree=2", summary["disagree"] == 2)
check("agree_pct=50", summary["agree_pct"] == 50.0)
check("has disagree_by_context", "disagree_by_context" in summary)
check("has human_low_score", "human_low_score_choices" in summary)
check("has ai_ignored", "ai_ignored_choices" in summary)

print("\n=== analyze empty ===")
empty_summary = analyze([])
check("empty total=0", empty_summary["total"] == 0)
check("empty agree_pct=0", empty_summary["agree_pct"] == 0.0)

print("\n=== format_report ===")
report = format_report(summary)
check("report is string", isinstance(report, str))
check("report has header", "Human Trace Analysis" in report)
check("report has agree count", "2" in report)

# === recommender ===
print("\n=== recommend ===")

current_params = {
    "score_supporter_crispin": 700,
    "score_supporter_lillie": 600,
    "score_supporter_boss": 900,
    "score_item_ultra_ball": 500,
}

recs = recommend(entries, current_params)
check("recs has adjustments", "adjustments" in recs)
check("recs has proposed", "proposed" in recs)
check("recs has details", "details" in recs)
check("recs has summary", "summary" in recs)
check("recs summary total", recs["summary"]["total_decisions"] == 4)
check("recs summary agree", recs["summary"]["agreement_pct"] == 50.0)

print("\n=== recommend empty ===")
empty_recs = recommend([], {})
check("empty recs no adjustments", len(empty_recs["adjustments"]) == 0)

shutil.rmtree(tmp)
# Clean up test trace dir if created
test_traces_dir = os.path.join(os.path.dirname(__file__), "web", "human_traces")
if os.path.isdir(test_traces_dir):
    for f in os.listdir(test_traces_dir):
        if "test_session" in f:
            os.remove(os.path.join(test_traces_dir, f))

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
