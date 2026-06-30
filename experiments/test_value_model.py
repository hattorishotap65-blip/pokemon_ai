"""Tests for value_model inference."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents", "raging_bolt"))

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0

def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond: _f += 1

print("=== model not present ===")
from experiments.agents.raging_bolt.value_model import (
    load_value_model, predict_state_value, model_available, _MODEL_PATH
)
# Reset loaded state
import experiments.agents.raging_bolt.value_model as vm
vm._LOADED = False
vm._MODEL = None

has_model = os.path.exists(_MODEL_PATH)
if not has_model:
    check("load returns False when no model", load_value_model() is False)
    check("model_available is False", model_available() is False)
    check("predict returns None", predict_state_value(None, 0) is None)
else:
    check("load returns True when model exists", load_value_model() is True)
    check("model_available is True", model_available() is True)

print("\n=== use_value_model=false ===")
# Verify params has use_value_model=false
import json
params_path = os.path.join(os.path.dirname(__file__), "agents", "raging_bolt", "params.json")
with open(params_path, encoding="utf-8") as f:
    params = json.load(f)
check("use_value_model is false", params.get("use_value_model") is False)
check("value_model_weight exists", "value_model_weight" in params)

print("\n%d/%d passed" % (_t - _f, _t))
if _f: sys.exit(1)
