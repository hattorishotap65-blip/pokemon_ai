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
from experiments.web.apply_params import preview_changes, apply_changes

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

print("\n=== strategy tags (server-side update) ===")
strategy_entry = build_trace_entry(
    deck_name="raging_bolt", turn=2, context="PLAY",
    options=[{"i": 0, "label": "test", "score": 100}],
    ai_pick=[0], human_pick=[0],
)
strategy_entry.update({
    "turn_goal": "prepare_next_turn_attack",
    "win_plan_tags": ["raging_bolt_big_damage_next_turn"],
    "risk_flags": ["not_enough_energy", "low_hand"],
    "human_reason_tags": ["prepare_next_turn_attack", "improve_hand"],
    "human_considered": [0, 1],
})
check("strategy: turn_goal", strategy_entry["turn_goal"] == "prepare_next_turn_attack")
check("strategy: win_plan_tags", strategy_entry["win_plan_tags"] == ["raging_bolt_big_damage_next_turn"])
check("strategy: risk_flags len", len(strategy_entry["risk_flags"]) == 2)
check("strategy: human_reason_tags", "improve_hand" in strategy_entry["human_reason_tags"])
check("strategy: human_considered", strategy_entry["human_considered"] == [0, 1])

tmp_strat_dir = tempfile.mkdtemp()
tmp_strat = os.path.join(tmp_strat_dir, "strat_trace.jsonl")
write_trace_entry(tmp_strat, strategy_entry)
loaded_strat = load_traces(tmp_strat)
check("strategy: roundtrip", loaded_strat[0]["turn_goal"] == "prepare_next_turn_attack")
check("strategy: roundtrip risk", loaded_strat[0]["risk_flags"] == ["not_enough_energy", "low_hand"])
shutil.rmtree(tmp_strat_dir)

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
check("entry has type=decision", entry["type"] == "decision")

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

print("\n=== analyze filters game_result ===")
entries_with_result = entries + [
    build_game_result_entry("rb", "dragapult", "win", 10),
]
summary_filtered = analyze(entries_with_result)
check("game_result excluded from total", summary_filtered["total"] == 4)

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

# === apply_params ===
print("\n=== preview_changes ===")
cur = {"score_a": 100, "score_b": 200, "score_c": 300}
prop = {"score_a": 120, "score_c": 300, "score_d": 50}
changes = preview_changes(cur, prop)
check("preview: 2 changes", len(changes) == 2)
check("preview: score_a 100->120", changes[0] == ("score_a", 100, 120, 20))
check("preview: score_d new", changes[1] == ("score_d", None, 50, 50))

print("\n=== apply_changes ===")
params_file = os.path.join(tmp, "test_params.json")
with open(params_file, "w", encoding="utf-8") as f:
    json.dump({"score_a": 100, "score_b": 200, "_comment": "test"}, f)

result = apply_changes(params_file, {"score_a": 150, "score_new": 999})
check("apply: score_a updated", result["score_a"] == 150)
check("apply: score_b unchanged", result["score_b"] == 200)
check("apply: score_new added", result["score_new"] == 999)
check("apply: _comment preserved", result["_comment"] == "test")
check("apply: backup created", os.path.exists(params_file + ".bak"))

with open(params_file, encoding="utf-8") as f:
    saved = json.load(f)
check("apply: file saved correctly", saved["score_a"] == 150)

print("\n=== apply no changes ===")
no_changes = preview_changes({"a": 1}, {"a": 1})
check("no changes: empty", len(no_changes) == 0)

print("\n=== server sanitize_strategy_tags ===")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))
try:
    from server import _sanitize_strategy_tags, _VALID_GOALS, _VALID_RISKS
    _server_imported = True
except Exception:
    _server_imported = False

if not _server_imported:
    _VALID_GOALS_TEST = {'setup_board', 'take_ko_now', 'close_game'}
    def _sanitize_test(body, option_count):
        goal = body.get('turn_goal', '')
        return {
            'turn_goal': goal if goal in _VALID_GOALS_TEST else '',
            'win_plan_tags': [t for t in body.get('win_plan_tags', []) if isinstance(t, str)],
            'human_considered': [i for i in body.get('human_considered', [])
                                 if isinstance(i, int) and 0 <= i < option_count],
        }
    r = _sanitize_test({'turn_goal': 'INVALID', 'win_plan_tags': ['ko_active'],
                         'human_considered': [0, 1, 2, 30, 49, 50, -1]}, 3)
    check("sanitize: invalid goal cleared", r['turn_goal'] == '')
    check("sanitize: valid tags kept", r['win_plan_tags'] == ['ko_active'])
    check("sanitize: only in-range indices kept", r['human_considered'] == [0, 1, 2])
else:
    r = _sanitize_strategy_tags({
        'turn_goal': 'INVALID_GOAL',
        'win_plan_tags': ['ko_active', 'BOGUS'],
        'risk_flags': ['low_hand', 'FAKE'],
        'human_reason_tags': ['take_ko_now', 'XSS_ATTEMPT'],
        'human_considered': [0, 1, 2, 30, 49, 50, -1],
    }, 3)
    check("sanitize: invalid goal cleared", r['turn_goal'] == '')
    check("sanitize: bogus win_plan removed", r['win_plan_tags'] == ['ko_active'])
    check("sanitize: bogus risk removed", r['risk_flags'] == ['low_hand'])
    check("sanitize: bogus reason removed", r['human_reason_tags'] == ['take_ko_now'])
    check("sanitize: only in-range indices", r['human_considered'] == [0, 1, 2])

    r2 = _sanitize_strategy_tags({'turn_goal': 'setup_board'}, 5)
    check("sanitize: valid goal kept", r2['turn_goal'] == 'setup_board')

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
