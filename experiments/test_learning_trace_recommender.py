"""
Tests for experiments/learning/trace_recommender.py.

Run: python experiments/test_learning_trace_recommender.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.trace_recommender import (
    build_tuning_recommendations, render_recommendation_report,
    _action_key_from_entry, _collect_zero_score_actions,
    _build_action_hotspots, _build_fallback_hotspots,
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


TRACES_WITH_ISSUES = [
    {"used_advisor": False, "fallback_reason": "all_scores_zero", "advisor_top": None,
     "candidates": [{"id": "end_turn", "type": "end"}, {"id": "attach_e", "type": "attach"}],
     "advisor_overrode_existing": False, "advisor_scores": [],
     "existing_top_index": 0, "advisor_top_index": -1},
    {"used_advisor": False, "fallback_reason": "all_scores_zero", "advisor_top": None,
     "candidates": [{"id": "retreat_0", "type": "retreat"}],
     "advisor_overrode_existing": False, "advisor_scores": [],
     "existing_top_index": 0, "advisor_top_index": -1},
    {"used_advisor": False, "fallback_reason": "all_scores_zero", "advisor_top": None,
     "candidates": [{"id": "attach_e2", "type": "attach"}],
     "advisor_overrode_existing": False, "advisor_scores": [],
     "existing_top_index": 0, "advisor_top_index": -1},
    {"used_advisor": False, "fallback_reason": "all_scores_zero", "advisor_top": None,
     "candidates": [{"id": "attach_e3", "type": "attach"}],
     "advisor_overrode_existing": False, "advisor_scores": [],
     "existing_top_index": 0, "advisor_top_index": -1},
    {"used_advisor": False, "fallback_reason": "all_scores_zero", "advisor_top": None,
     "candidates": [{"id": "attach_e4", "type": "attach"}],
     "advisor_overrode_existing": False, "advisor_scores": [],
     "existing_top_index": 0, "advisor_top_index": -1},
    {"used_advisor": True, "fallback_reason": None, "advisor_top": "play_crispin",
     "candidates": [{"id": "play_crispin", "type": "supporter"}],
     "advisor_overrode_existing": True, "advisor_top_index": 0, "existing_top_index": 1,
     "advisor_scores": [{"action_id": "play_crispin", "score": 55.0}],
     "state_summary": {"active": "Raging Bolt ex"}},
]

TRACES_HEALTHY = [
    {"used_advisor": True, "fallback_reason": None, "advisor_top": "play_crispin",
     "candidates": [{"id": "play_crispin", "type": "supporter"}],
     "advisor_overrode_existing": False, "advisor_top_index": 0, "existing_top_index": 0,
     "advisor_scores": [{"action_id": "play_crispin", "score": 55.0}]},
    {"used_advisor": True, "fallback_reason": None, "advisor_top": "use_teal_dance",
     "candidates": [{"id": "use_teal_dance", "type": "ability"}],
     "advisor_overrode_existing": False, "advisor_top_index": 0, "existing_top_index": 0,
     "advisor_scores": [{"action_id": "use_teal_dance", "score": 50.0}]},
]

print("=== _action_key_from_entry ===")
check("advisor_top present", _action_key_from_entry({"advisor_top": "play_crispin"}) == "play_crispin")
check("no advisor_top, uses candidate", _action_key_from_entry({"candidates": [{"id": "x"}]}) == "x")
check("empty entry", _action_key_from_entry({}) == "unknown")

print("\n=== _collect_zero_score_actions ===")
zero_actions = _collect_zero_score_actions(TRACES_WITH_ISSUES)
check("counts attach type", zero_actions.get("attach", 0) >= 3)
check("counts end type", zero_actions.get("end", 0) >= 1)

print("\n=== _build_action_hotspots ===")
hotspots = _build_action_hotspots(TRACES_WITH_ISSUES)
check("returns list", isinstance(hotspots, list))
check("has play_crispin", any(h["action"] == "play_crispin" for h in hotspots))
crispin_h = [h for h in hotspots if h["action"] == "play_crispin"][0]
check("hotspot has count", crispin_h["count"] == 1)
check("hotspot has override_count", crispin_h["override_count"] == 1)
check("hotspot has avg_score", crispin_h["avg_score"] == 55.0)
check("hotspot has example_active", crispin_h["example_active"] == "Raging Bolt ex")

print("\n=== _build_fallback_hotspots ===")
fb_hs = _build_fallback_hotspots(TRACES_WITH_ISSUES)
check("returns list", isinstance(fb_hs, list))
check("has all_scores_zero", any(h["reason"] == "all_scores_zero" for h in fb_hs))
check("has example_types", len(fb_hs[0].get("example_types", {})) > 0)

print("\n=== build_tuning_recommendations (issues) ===")
recs = build_tuning_recommendations(TRACES_WITH_ISSUES)
check("returns dict", isinstance(recs, dict))
check("has signals", "signals" in recs)
check("has recommendations", len(recs.get("recommendations", [])) > 0)
check("has action_hotspots", "action_hotspots" in recs)
check("has fallback_hotspots", "fallback_hotspots" in recs)

issues = [r["issue"] for r in recs["recommendations"]]
check("detects all_scores_zero (>=5)", "all_scores_zero_rate_high" in issues)

rec0 = recs["recommendations"][0]
check("rec has category", "category" in rec0)
check("rec has title", "title" in rec0)
check("rec has reason", "reason" in rec0)
check("rec has suggested_action", "suggested_action" in rec0)

signals = [s["signal"] for s in recs.get("signals", [])]
check("signal: high_zero_score_rate", "high_zero_score_rate" in signals)

print("\n=== build_tuning_recommendations (healthy) ===")
recs_h = build_tuning_recommendations(TRACES_HEALTHY)
check("healthy: no high-priority issues", all(
    r["priority"] != "high" for r in recs_h["recommendations"]
))

print("\n=== build_tuning_recommendations (empty) ===")
recs_e = build_tuning_recommendations([])
check("empty: has no_issues_found", any(
    r["issue"] == "no_issues_found" for r in recs_e["recommendations"]
))

print("\n=== build_tuning_recommendations (weights_missing) ===")
wm_traces = [{"used_advisor": False, "fallback_reason": "weights_missing",
              "candidates": [], "advisor_overrode_existing": False,
              "advisor_scores": [], "advisor_top_index": -1, "existing_top_index": 0}]
recs_wm = build_tuning_recommendations(wm_traces)
check("weights_missing detected", any(
    r["issue"] == "weights_missing" for r in recs_wm["recommendations"]
))

print("\n=== render_recommendation_report ===")
report = render_recommendation_report(recs)
check("report is string", isinstance(report, str))
check("contains Summary", "Summary" in report)
check("contains Key Signals", "Key Signals" in report)
check("contains Recommendations", "Recommendations" in report)
check("contains Fallback Hotspots", "Fallback Hotspots" in report)
check("contains Action Hotspots", "Action Hotspots" in report)
check("contains Next Suggested PR", "Next Suggested PR" in report)
check("contains all_scores_zero", "all_scores_zero" in report)
check("contains Suggestion", "Suggestion" in report)

report_empty = render_recommendation_report(recs_e)
check("empty report: no crash", isinstance(report_empty, str))

print("\n=== CLI smoke ===")
result = subprocess.run([
    sys.executable, "experiments/learning/recommend_from_traces.py",
    "--trace", "experiments/learning/sample_traces/sample_tuning_trace.jsonl",
], capture_output=True, text=True)
check("CLI runs", result.returncode == 0)

result_missing = subprocess.run([
    sys.executable, "experiments/learning/recommend_from_traces.py",
    "--trace", "/nonexistent/trace.jsonl",
], capture_output=True, text=True)
check("CLI missing file: no crash", result_missing.returncode == 0)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
