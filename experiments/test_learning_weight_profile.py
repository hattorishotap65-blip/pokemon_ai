"""
Tests for experiments/learning/weight_profile.py.

Run: python experiments/test_learning_weight_profile.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.learning.weight_profile import load_weight_profile

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


print("=== load_weight_profile ===")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"a": 1.0, "b": 2.5}, f)
    valid_path = f.name

w = load_weight_profile(valid_path)
check("valid JSON loads correctly", w == {"a": 1.0, "b": 2.5})
os.unlink(valid_path)

check("missing file returns empty dict", load_weight_profile("/nonexistent/path.json") == {})

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"fallback_key": 10.0}, f)
    fb_path = f.name

w2 = load_weight_profile("/nonexistent/path.json", fallback_path=fb_path)
check("missing file uses fallback", w2 == {"fallback_key": 10.0})
os.unlink(fb_path)

check("missing file + no fallback returns empty", load_weight_profile("/no1.json", "/no2.json") == {})

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    f.write("not valid json{{{")
    bad_path = f.name

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"rescued": 5.0}, f)
    rescue_path = f.name

w3 = load_weight_profile(bad_path, fallback_path=rescue_path)
check("invalid JSON falls back", w3 == {"rescued": 5.0})
os.unlink(bad_path)
os.unlink(rescue_path)

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"good": 1.0, "bad_str": "hello", "bad_list": [1], "ok_int": 3}, f)
    mixed_path = f.name

w4 = load_weight_profile(mixed_path)
check("non-numeric values ignored", "bad_str" not in w4 and "bad_list" not in w4)
check("numeric values kept", w4.get("good") == 1.0 and w4.get("ok_int") == 3.0)
os.unlink(mixed_path)

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({"bool_true": True, "bool_false": False, "real_num": 42.0}, f)
    bool_path = f.name

w5 = load_weight_profile(bool_path)
check("bool True excluded", "bool_true" not in w5)
check("bool False excluded", "bool_false" not in w5)
check("real number kept alongside bools", w5.get("real_num") == 42.0)
os.unlink(bool_path)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
