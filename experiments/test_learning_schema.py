"""
Tests for experiments/learning/schema.py.

Run: python experiments/test_learning_schema.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.schema import validate_entry, load_logs

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


VALID_ENTRY = {
    "match_id": "test_001",
    "turn": 1,
    "legal_actions": [
        {"id": "a1", "label": "action 1", "type": "item"},
        {"id": "a2", "label": "action 2", "type": "attack"},
    ],
    "chosen_action_id": "a1",
}

print("=== validate_entry ===")

check("valid entry has no errors", validate_entry(VALID_ENTRY) == [])

check("missing match_id", len(validate_entry({"turn": 1, "legal_actions": [], "chosen_action_id": "x"})) > 0)

check("missing turn", len(validate_entry({"match_id": "x", "legal_actions": [], "chosen_action_id": "x"})) > 0)

check("missing legal_actions", len(validate_entry({"match_id": "x", "turn": 1, "chosen_action_id": "x"})) > 0)

check("missing chosen_action_id", len(validate_entry({"match_id": "x", "turn": 1, "legal_actions": []})) > 0)

check("legal_actions item missing id", len(validate_entry({
    "match_id": "x", "turn": 1, "chosen_action_id": "a1",
    "legal_actions": [{"label": "no id"}],
})) > 0)

check("duplicate action id", len(validate_entry({
    "match_id": "x", "turn": 1, "chosen_action_id": "a1",
    "legal_actions": [{"id": "a1"}, {"id": "a1"}],
})) > 0)

check("chosen_action_id not in legal_actions", len(validate_entry({
    "match_id": "x", "turn": 1, "chosen_action_id": "missing",
    "legal_actions": [{"id": "a1"}, {"id": "a2"}],
})) > 0)

check("non-dict entry", len(validate_entry("not a dict")) > 0)

check("legal_actions is string", len(validate_entry({
    "match_id": "x", "turn": 1, "chosen_action_id": "a1",
    "legal_actions": "not a list",
})) > 0)

check("legal_actions is dict", len(validate_entry({
    "match_id": "x", "turn": 1, "chosen_action_id": "a1",
    "legal_actions": {"id": "a1"},
})) > 0)

print("\n=== load_logs ===")

NON_LIST_ENTRY = {
    "match_id": "x", "turn": 1, "chosen_action_id": "a1",
    "legal_actions": "not a list",
}

with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    f.write(json.dumps(VALID_ENTRY) + "\n")
    f.write("not json\n")
    f.write(json.dumps({"bad": "entry"}) + "\n")
    f.write(json.dumps(NON_LIST_ENTRY) + "\n")
    f.write(json.dumps(VALID_ENTRY) + "\n")
    f.write("\n")
    tmp_path = f.name

logs = load_logs(tmp_path)
os.unlink(tmp_path)

check("load_logs skips invalid JSON", len(logs) == 2)
check("load_logs skips invalid entries", all(validate_entry(e) == [] for e in logs))
check("load_logs returns valid entries", logs[0]["match_id"] == "test_001")

with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    f.write("")
    tmp_empty = f.name

empty_logs = load_logs(tmp_empty)
os.unlink(tmp_empty)
check("load_logs handles empty file", empty_logs == [])

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
