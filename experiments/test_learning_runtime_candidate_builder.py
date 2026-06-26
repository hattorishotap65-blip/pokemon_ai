"""
Tests for experiments/learning/runtime_candidate_builder.py.

Run: python experiments/test_learning_runtime_candidate_builder.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.runtime_candidate_builder import (
    build_runtime_candidate,
    build_runtime_candidates,
    build_runtime_state,
    _infer_option_type,
    _safe_attr,
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


# Dummy objects to simulate runtime without cg.api
class DummyEnum:
    def __init__(self, val):
        self.value = val
    def __eq__(self, other):
        if isinstance(other, DummyEnum):
            return self.value == other.value
        return self.value == other
    def __hash__(self):
        return hash(self.value)

class DummyOption:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class DummyPlayer:
    def __init__(self):
        self.active = []
        self.bench = []
        self.hand = []
        self.discard = []
        self.prize = [None, None, None, None, None, None]
        self.handCount = 0
        self.deckCount = 0

class DummySelect:
    def __init__(self, options=None):
        self.option = options or []
        self.context = None
        self.maxCount = 1

class DummyObs:
    pass

class DummyPolicy:
    def __init__(self, options=None):
        self.obs = DummyObs()
        self.select = DummySelect(options)
        self.my_index = 0
        self.me = DummyPlayer()
        self.opponent = DummyPlayer()


print("=== _safe_attr ===")

obj = DummyOption(x=42)
check("existing attr", _safe_attr(obj, "x") == 42)
check("missing attr", _safe_attr(obj, "y", "default") == "default")
check("none object", _safe_attr(None, "x", "fallback") == "fallback")

print("\n=== build_runtime_candidate ===")

# Test with minimal option (no cg.api available in test)
opt = DummyOption(type="test_type")
policy = DummyPolicy()
cand = build_runtime_candidate(policy, opt, 0)
check("returns id", "id" in cand and len(cand["id"]) > 0)
check("returns label", "label" in cand)
check("returns type", "type" in cand)
check("returns original_index", cand.get("original_index") == 0)

opt2 = DummyOption(type="something")
cand2 = build_runtime_candidate(policy, opt2, 3)
check("original_index preserved", cand2["original_index"] == 3)

print("\n=== build_runtime_candidates ===")

opts = [DummyOption(type="a"), DummyOption(type="b"), DummyOption(type="c")]
policy3 = DummyPolicy(opts)
cands = build_runtime_candidates(policy3)
check("returns same count as options", len(cands) == 3)
check("all have original_index", all("original_index" in c for c in cands))
check("indices are 0,1,2", [c["original_index"] for c in cands] == [0, 1, 2])

empty_policy = DummyPolicy([])
check("empty options -> empty list", build_runtime_candidates(empty_policy) == [])

print("\n=== build_runtime_state ===")

# Without cg.api/main, should return {} gracefully
state = build_runtime_state(policy)
check("returns dict", isinstance(state, dict))

print("\n=== edge cases ===")

bad_opt = "not an option"
cand_bad = build_runtime_candidate(policy, bad_opt, 0)
check("non-option object -> no crash", isinstance(cand_bad, dict) and "type" in cand_bad)

none_policy = DummyPolicy()
none_policy.select = DummySelect(None)
check("None options -> empty list", build_runtime_candidates(none_policy) == [])

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
