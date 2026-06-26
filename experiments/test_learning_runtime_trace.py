"""
Tests for experiments/learning/runtime_trace.py.

Run: python experiments/test_learning_runtime_trace.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.runtime_trace import (
    trace_enabled, build_trace_entry, write_advisor_trace,
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


def _set_env(key, val):
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val


print("=== trace_enabled ===")

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", None)
check("unset -> disabled", not trace_enabled())

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", "0")
check("'0' -> disabled", not trace_enabled())

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", "1")
check("'1' -> enabled", trace_enabled())

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", None)

print("\n=== build_trace_entry ===")

state = {"active": "Raging Bolt ex", "prizes_remaining": 4, "opponent_active": "Lucario", "opponent_prizes": 3}
cands = [
    {"id": "play_crispin", "label": "Crispin", "type": "supporter"},
    {"id": "attack_bellowing", "label": "Bellowing Thunder", "type": "attack"},
]
ranked = [
    {"action_id": "play_crispin", "score": 55.0, "original_index": 0},
    {"action_id": "attack_bellowing", "score": -20.0, "original_index": 1},
]
existing_scores = [100.0, 200.0]
existing_ranked = [1, 0]

entry = build_trace_entry(state, cands, ranked, existing_scores, existing_ranked, [0], None)
check("has ts", "ts" in entry and entry["ts"] > 0)
check("used_advisor true when no fallback", entry["used_advisor"] is True)
check("advisor_top is crispin", entry["advisor_top"] == "play_crispin")
check("advisor_top_index is 0", entry["advisor_top_index"] == 0)
check("existing_top_index is 1", entry["existing_top_index"] == 1)
check("advisor_overrode_existing true", entry["advisor_overrode_existing"] is True)
check("selected_indices present", entry["selected_indices"] == [0])
check("advisor_scores present", len(entry["advisor_scores"]) == 2)
check("candidates summary present", len(entry["candidates"]) == 2)
check("state_summary has active", entry["state_summary"]["active"] == "Raging Bolt ex")

entry_fb = build_trace_entry(state, cands, None, existing_scores, existing_ranked, [1, 0], "weights_missing")
check("fallback entry: used_advisor false", entry_fb["used_advisor"] is False)
check("fallback entry: reason is weights_missing", entry_fb["fallback_reason"] == "weights_missing")
check("fallback entry: advisor_overrode false", entry_fb["advisor_overrode_existing"] is False)

entry_same = build_trace_entry(state, cands, [{"action_id": "x", "score": 1.0, "original_index": 1}], existing_scores, existing_ranked, [1], None)
check("same top: advisor_overrode false", entry_same["advisor_overrode_existing"] is False)

entry_empty = build_trace_entry({}, [], None, [], [], [], "no_candidates")
check("empty inputs: no crash", isinstance(entry_empty, dict))

print("\n=== write_advisor_trace ===")

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", None)
write_advisor_trace({"test": True})
check("disabled: write does nothing (no crash)", True)

with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
    tmp_trace = f.name

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_TRACE_PATH", tmp_trace)

write_advisor_trace(entry)
write_advisor_trace(entry_fb)

with open(tmp_trace, encoding="utf-8") as f:
    lines = [l.strip() for l in f if l.strip()]
check("wrote 2 trace lines", len(lines) == 2)

first = json.loads(lines[0])
check("first trace has used_advisor", "used_advisor" in first)
check("first trace is valid JSON", first["advisor_top"] == "play_crispin")

os.unlink(tmp_trace)

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", "1")
_set_env("POKEMON_AI_TRACE_PATH", "/nonexistent/dir/deep/file.jsonl")
write_advisor_trace(entry)
check("invalid path: no crash", True)

_set_env("POKEMON_AI_TRACE_LEARNED_WEIGHTS", None)
_set_env("POKEMON_AI_TRACE_PATH", None)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
