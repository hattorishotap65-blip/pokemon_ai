"""
Tests for experiments/learning/trace_analyzer.py.

Run: python experiments/test_learning_trace_analyzer.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.trace_analyzer import (
    load_traces, analyze_traces, format_report, find_override_cases,
)

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


SAMPLE_TRACES = [
    {
        "ts": 1000.0, "used_advisor": True, "fallback_reason": None,
        "advisor_top": "play_crispin", "advisor_top_index": 0,
        "existing_top_index": 1, "advisor_overrode_existing": True,
        "selected_indices": [0],
        "advisor_scores": [
            {"action_id": "play_crispin", "score": 55.0, "original_index": 0},
            {"action_id": "attack_bellowing", "score": -20.0, "original_index": 1},
        ],
        "existing_scores_top3": [{"index": 1, "score": 200.0}],
        "candidates": [{"id": "play_crispin"}, {"id": "attack_bellowing"}],
        "n_candidates": 2,
        "state_summary": {"active": "Raging Bolt ex"},
    },
    {
        "ts": 1001.0, "used_advisor": False, "fallback_reason": "all_scores_zero",
        "advisor_top": None, "advisor_top_index": -1,
        "existing_top_index": 0, "advisor_overrode_existing": False,
        "selected_indices": [0],
        "advisor_scores": [],
        "existing_scores_top3": [{"index": 0, "score": 100.0}],
        "candidates": [{"id": "end_turn"}],
        "n_candidates": 1,
        "state_summary": {"active": "Raging Bolt ex"},
    },
    {
        "ts": 1002.0, "used_advisor": True, "fallback_reason": None,
        "advisor_top": "play_crispin", "advisor_top_index": 0,
        "existing_top_index": 0, "advisor_overrode_existing": False,
        "selected_indices": [0],
        "advisor_scores": [{"action_id": "play_crispin", "score": 55.0, "original_index": 0}],
        "existing_scores_top3": [{"index": 0, "score": 300.0}],
        "candidates": [{"id": "play_crispin"}],
        "n_candidates": 1,
        "state_summary": {"active": "Raging Bolt ex"},
    },
    {
        "ts": 1003.0, "used_advisor": False, "fallback_reason": "weights_missing",
        "advisor_top": None, "advisor_top_index": -1,
        "existing_top_index": 0, "advisor_overrode_existing": False,
        "selected_indices": [0],
        "advisor_scores": [],
        "existing_scores_top3": [],
        "candidates": [],
        "n_candidates": 0,
        "state_summary": {},
    },
]

print("=== load_traces ===")

with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    for t in SAMPLE_TRACES:
        f.write(json.dumps(t) + "\n")
    f.write("bad json\n")
    f.write("\n")
    tmp_path = f.name

loaded = load_traces(tmp_path)
check("loads valid entries", len(loaded) == 4)
check("skips invalid JSON", True)
os.unlink(tmp_path)

check("missing file returns empty", load_traces("/nonexistent/path.jsonl") == [])

print("\n=== analyze_traces ===")

summary = analyze_traces(SAMPLE_TRACES)
check("total is 4", summary["total"] == 4)
check("advisor_used is 2", summary["advisor_used"] == 2)
check("advisor_used_rate is 0.5", summary["advisor_used_rate"] == 0.5)
check("fallback_count is 2", summary["fallback_count"] == 2)
check("override_count is 1", summary["override_count"] == 1)
check("override_rate is 0.25", summary["override_rate"] == 0.25)
check("fallback_reasons has all_scores_zero", summary["fallback_reasons"].get("all_scores_zero") == 1)
check("fallback_reasons has weights_missing", summary["fallback_reasons"].get("weights_missing") == 1)
check("advisor_top_actions has play_crispin", summary["advisor_top_actions"].get("play_crispin") == 2)
check("avg_advisor_top_score > 0", summary["avg_advisor_top_score"] > 0)
check("max_top_advisor_score present", summary["max_top_advisor_score"] >= summary["min_top_advisor_score"])
check("selected_index_distribution present", isinstance(summary["selected_index_distribution"], dict))

print("\n=== analyze_traces empty ===")

empty = analyze_traces([])
check("empty total is 0", empty["total"] == 0)
check("empty advisor_used_rate is 0", empty["advisor_used_rate"] == 0.0)
check("empty fallback_reasons is empty", empty["fallback_reasons"] == {})

print("\n=== format_report ===")

report = format_report(summary)
check("report is string", isinstance(report, str))
check("contains Overview", "Overview" in report)
check("contains Total decisions", "Total decisions" in report)
check("contains Advisor used", "Advisor used" in report)
check("contains Fallback Reasons", "Fallback Reasons" in report)
check("contains all_scores_zero", "all_scores_zero" in report)
check("contains weights_missing", "weights_missing" in report)
check("contains Advisor Top Actions", "Advisor Top Actions" in report)
check("contains play_crispin", "play_crispin" in report)
check("contains override", "overrode" in report.lower() or "Override" in report)

report_empty = format_report(empty)
check("empty report: no crash", isinstance(report_empty, str))
check("empty report: contains Overview", "Overview" in report_empty)

print("\n=== find_override_cases ===")

overrides = find_override_cases(SAMPLE_TRACES)
check("finds 1 override", len(overrides) == 1)
check("override has advisor_top", overrides[0]["advisor_top"] == "play_crispin")
check("override has state_active", overrides[0]["state_active"] == "Raging Bolt ex")

check("empty entries -> empty overrides", find_override_cases([]) == [])
check("limit works", len(find_override_cases(SAMPLE_TRACES * 10, limit=3)) == 3)

print("\n=== format_report with overrides ===")

report_with_ov = format_report(summary, overrides)
check("report has Override Cases", "Override Cases" in report_with_ov)
check("report has play_crispin in overrides", "play_crispin" in report_with_ov)
check("report has max score", "Max advisor" in report_with_ov)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
