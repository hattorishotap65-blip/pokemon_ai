"""Tests for experiments/agents/raging_bolt/ agent and params."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


AGENT_DIR = os.path.join(os.path.dirname(__file__), "agents", "raging_bolt")
DECK_DIR = os.path.join(os.path.dirname(__file__), "decks")

print("=== files exist ===")
check("main.py exists", os.path.exists(os.path.join(AGENT_DIR, "main.py")))
check("params.json exists", os.path.exists(os.path.join(AGENT_DIR, "params.json")))
check("deck csv exists", os.path.exists(os.path.join(DECK_DIR, "raging_bolt_ogerpon.csv")))

print("\n=== params.json ===")
with open(os.path.join(AGENT_DIR, "params.json"), encoding="utf-8") as f:
    params = json.load(f)

check("params is dict", isinstance(params, dict))
check("has score keys", any(k.startswith("score_") for k in params))
check("bellowing_thunder key", "score_attack_bellowing_thunder" in params)
check("teal_dance key", "score_ability_teal_dance" in params)
check("end_turn key", "score_end_turn" in params)
check("all values numeric", all(
    isinstance(v, (int, float)) for k, v in params.items() if not k.startswith("_")
))

print("\n=== deck ===")
with open(os.path.join(DECK_DIR, "raging_bolt_ogerpon.csv"), encoding="utf-8") as f:
    deck = [int(l.strip()) for l in f if l.strip()]

check("deck has 60 cards", len(deck) == 60)
check("Raging Bolt ex x4", deck.count(63) == 4)
check("Ogerpon ex x4", deck.count(96) == 4)

print("\n=== main.py syntax ===")
main_path = os.path.join(AGENT_DIR, "main.py")
with open(main_path, encoding="utf-8") as f:
    code = f.read()
try:
    compile(code, main_path, "exec")
    check("main.py compiles", True)
except SyntaxError as e:
    check("main.py compiles: %s" % e, False)

print("\n=== deck_registry integration ===")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))
from deck_registry import deck_csv_path, agent_main_path, available_decks

check("raging_bolt available", "raging_bolt" in available_decks())
rb_csv = deck_csv_path("raging_bolt")
rb_agent = agent_main_path("raging_bolt")
check("csv points to raging_bolt_ogerpon.csv",
      rb_csv is not None and "raging_bolt_ogerpon.csv" in rb_csv)
check("agent points to raging_bolt main.py",
      rb_agent is not None and "raging_bolt" in rb_agent and rb_agent.endswith("main.py"))

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
