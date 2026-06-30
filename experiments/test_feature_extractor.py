"""Tests for feature_extractor."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents", "raging_bolt"))

from experiments.agents.raging_bolt.feature_extractor import extract_features, FEATURE_KEYS

PASS = "[PASS]"
FAIL = "[FAIL]"
_f = 0
_t = 0

def check(label, cond):
    global _f, _t
    _t += 1
    print("  %s  %s" % (PASS if cond else FAIL, label))
    if not cond: _f += 1

print("=== FEATURE_KEYS ===")
check("has keys", len(FEATURE_KEYS) >= 30)
check("my_prizes in keys", "my_prizes" in FEATURE_KEYS)
check("bolt_ready in keys", "bolt_ready" in FEATURE_KEYS)
check("field_ready in keys", "field_ready" in FEATURE_KEYS)
check("can_ko_active in keys", "can_ko_active" in FEATURE_KEYS)

print("\n=== keys stable ===")
expected = {"my_prizes", "opp_prizes", "prize_diff", "bolt_ready",
            "hand_size", "deck_count", "field_ready", "active_ko_risk"}
check("expected keys subset", expected.issubset(set(FEATURE_KEYS)))

print("\n=== energy card IDs are correct ===")
from experiments.agents.raging_bolt.feature_extractor import GRASS, LIGHTNING, FIGHTING
check("GRASS == 1", GRASS == 1)
check("LIGHTNING == 4", LIGHTNING == 4)
check("FIGHTING == 6", FIGHTING == 6)

print("\n%d/%d passed" % (_t - _f, _t))
if _f: sys.exit(1)
