"""Tests for disagreement_review_builder."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.human_trace_writer import (
    build_trace_entry, build_game_result_entry, write_trace_entry,
)
from experiments.web.disagreement_review_builder import (
    extract_items, format_report, build_initial_label, merge_labels,
    load_labels_jsonl, write_labels_jsonl, _make_review_id,
)

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0


def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond:
        _f += 1


def _write_trace(tmpdir, name, entries):
    path = os.path.join(tmpdir, name)
    for e in entries:
        write_trace_entry(path, e)
    return path


# === empty input ===
print("=== empty input ===")
check("extract_items: empty file list -> []", extract_items([]) == [])
check("format_report: no crash on empty", isinstance(format_report([], 0), str))

with tempfile.TemporaryDirectory() as tmp:
    # === non-MAIN excluded ===
    print("\n=== non-MAIN excluded ===")
    e_hand = build_trace_entry("rb", 1, "TO_HAND",
        [{"i": 0, "label": "A", "score": 500, "type": 3},
         {"i": 1, "label": "B", "score": 300, "type": 3}],
        ai_pick=[0], human_pick=[1])
    fp = _write_trace(tmp, "t1.jsonl", [e_hand, build_game_result_entry("rb", "drag", "win", 5)])
    items = extract_items([fp])
    check("non-MAIN: excluded", len(items) == 0)

    # === agreement excluded (no risk) ===
    print("\n=== agreement excluded ===")
    e_agree = build_trace_entry("rb", 1, "MAIN",
        [{"i": 0, "label": "A", "score": 500, "type": 13}],
        ai_pick=[0], human_pick=[0])
    fp2 = _write_trace(tmp, "t2.jsonl", [e_agree, build_game_result_entry("rb", "drag", "win", 5)])
    items2 = extract_items([fp2])
    check("agree (no risk): excluded", len(items2) == 0)

    # === disagreement included ===
    print("\n=== disagreement included ===")
    e_dis = build_trace_entry("rb", 3, "MAIN",
        [{"i": 0, "label": "Attack", "score": 2000, "type": 13, "cardId": 63},
         {"i": 1, "label": "Crispin", "score": 1300, "type": 7, "cardId": 1198}],
        ai_pick=[0], human_pick=[1],
        my_active={"id": 63, "hp": 200, "maxHp": 240, "energy": 3},
        opp_active={"id": 100, "hp": 320, "maxHp": 320, "energy": 2},
        my_prizes=4, opp_prizes=4)
    e_dis.update({"turn_goal": "prepare_next_turn_attack", "agent_goals": ["take_ko_now"],
                  "agent_risks": [], "risk_flags": []})
    fp3 = _write_trace(tmp, "t3.jsonl", [e_dis, build_game_result_entry("rb", "drag", "loss", 8)])
    items3 = extract_items([fp3])
    check("disagreement: 1 item", len(items3) == 1)
    check("disagreement: is_disagreement True", items3[0]["is_disagreement"] is True)
    check("disagreement: result_win 0", items3[0]["result_win"] == 0)
    check("disagreement: category set", bool(items3[0]["category"]))
    check("disagreement: ai_action set", items3[0]["ai_action"] == "Attack")
    check("disagreement: human_action set", items3[0]["human_action"] == "Crispin")
    check("disagreement: score_gap", items3[0]["score_gap"] == 700)

    # === agreement_bad included (agree but risky + loss) ===
    print("\n=== agreement_bad included ===")
    e_bad = build_trace_entry("rb", 4, "MAIN",
        [{"i": 0, "label": "Attack", "score": 1500, "type": 13}],
        ai_pick=[0], human_pick=[0],
        my_prizes=3, opp_prizes=3)
    e_bad.update({"risk_flags": ["no_next_attacker"], "agent_risks": []})
    fp4 = _write_trace(tmp, "t4.jsonl", [e_bad, build_game_result_entry("rb", "drag", "loss", 9)])
    items4 = extract_items([fp4])
    check("agreement_bad: included", len(items4) == 1)
    check("agreement_bad: flagged", items4[0]["is_agreement_bad"] is True)
    check("agreement_bad: is_disagreement False", items4[0]["is_disagreement"] is False)

    items4_off = extract_items([fp4], include_agreement_bad=False)
    check("agreement_bad: excluded when disabled", len(items4_off) == 0)

    # === review_id stability ===
    print("\n=== review_id stability ===")
    rid1 = _make_review_id(fp3, 1, 3, 0)
    rid2 = _make_review_id(fp3, 1, 3, 0)
    rid3 = _make_review_id(fp3, 1, 3, 1)
    check("review_id: deterministic", rid1 == rid2)
    check("review_id: differs by decision_index", rid1 != rid3)

    # === report rendering ===
    print("\n=== report rendering ===")
    report = format_report(items3 + items4, total_main_decisions=10)
    check("report: is string", isinstance(report, str))
    check("report: has summary table", "Total MAIN decisions" in report)
    check("report: has category breakdown", "Category Breakdown" in report)
    check("report: has priority order", "Priority Review Order" in report)
    check("report: has review item block", "## Review item" in report)
    check("report: has suggested labels", "human_better / agent_better" in report)

    # === labels jsonl: initial generation ===
    print("\n=== labels jsonl ===")
    label = build_initial_label(items3[0])
    check("label: has review_id", label["review_id"] == items3[0]["review_id"])
    check("label: label blank", label["label"] == "")
    check("label: created_from", label["created_from"] == "human_trace")

    labels_path = os.path.join(tmp, "disagreement_labels.jsonl")
    merged = merge_labels(labels_path, items3)
    check("merge_labels: 1 new record", len(merged) == 1)
    write_labels_jsonl(labels_path, merged)
    check("write_labels_jsonl: file exists", os.path.exists(labels_path))

    # === merge_labels preserves existing human-filled labels ===
    print("\n=== merge preserves labels ===")
    loaded = load_labels_jsonl(labels_path)
    rid = items3[0]["review_id"]
    loaded[rid]["label"] = "human_better"
    loaded[rid]["confidence"] = "high"
    write_labels_jsonl(labels_path, list(loaded.values()))

    merged2 = merge_labels(labels_path, items3)
    rec = next(r for r in merged2 if r["review_id"] == rid)
    check("merge_labels: preserves filled label", rec["label"] == "human_better")
    check("merge_labels: preserves confidence", rec["confidence"] == "high")

print("\n%d/%d passed" % (_t - _f, _t))
if _f:
    sys.exit(1)
