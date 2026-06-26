"""Tests for experiments/web/deck_registry.py and integration helpers."""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))

from experiments.web.deck_registry import (
    DECKS, resolve_deck_dir, available_decks,
    deck_csv_path, agent_main_path,
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


print("=== DECKS registry ===")
check("DECKS has entries", len(DECKS) >= 5)
check("lucario_v3 in DECKS", "lucario_v3" in DECKS)
check("dragapult in DECKS", "dragapult" in DECKS)
for name, (display, spec) in DECKS.items():
    check("%s display is string" % name, isinstance(display, str) and len(display) > 0)
    valid = (isinstance(spec, str) and (spec.startswith("agents/") or spec == "@@PROJECT_ROOT")) \
            or isinstance(spec, dict)
    check("%s spec is valid" % name, valid)

print("\n=== my_deck (project root) ===")
check("my_deck in DECKS", "my_deck" in DECKS)
check("my_deck resolves", resolve_deck_dir("my_deck") is not None)
check("my_deck deck_csv", deck_csv_path("my_deck") is not None)
check("my_deck agent_main", agent_main_path("my_deck") is not None)

print("\n=== raging_bolt (dict spec) ===")
check("raging_bolt in DECKS", "raging_bolt" in DECKS)
check("raging_bolt resolves", resolve_deck_dir("raging_bolt") is not None)
rb_csv = deck_csv_path("raging_bolt")
check("raging_bolt deck_csv exists", rb_csv is not None and os.path.exists(rb_csv))
rb_agent = agent_main_path("raging_bolt")
check("raging_bolt agent_main exists", rb_agent is not None and os.path.exists(rb_agent))
if rb_csv:
    with open(rb_csv) as f:
        cards = [l.strip() for l in f if l.strip()]
    check("raging_bolt has 60 cards", len(cards) == 60)

print("\n=== raging_bolt path correctness ===")
rb_csv = deck_csv_path("raging_bolt")
rb_agent = agent_main_path("raging_bolt")
check("raging_bolt csv is raging_bolt_ogerpon.csv",
      rb_csv is not None and "raging_bolt_ogerpon.csv" in rb_csv)
check("raging_bolt csv is NOT root deck.csv",
      rb_csv is not None and not rb_csv.endswith(os.sep + "deck.csv"))
check("raging_bolt agent is main.py",
      rb_agent is not None and rb_agent.endswith("main.py"))

print("\n=== resolve_deck_dir (no agents) ===")
tmp = tempfile.mkdtemp()
check("missing deck -> None", resolve_deck_dir("dragapult", tmp) is None)
check("unknown name -> None", resolve_deck_dir("nonexistent", tmp) is None)
# my_deck always resolves (project root), so available has at least 1
check("available_decks includes my_deck", "my_deck" in available_decks(tmp))

print("\n=== resolve_deck_dir (with mock agents) ===")
mock_deck = os.path.join(tmp, "agents", "dragapult")
os.makedirs(mock_deck)
with open(os.path.join(mock_deck, "deck.csv"), "w") as f:
    f.write("1\n2\n3\n")
with open(os.path.join(mock_deck, "main.py"), "w") as f:
    f.write("# mock\n")

check("dragapult resolves", resolve_deck_dir("dragapult", tmp) is not None)
check("dragapult path correct",
      os.path.normpath(resolve_deck_dir("dragapult", tmp)) == os.path.normpath(mock_deck))
check("available_decks includes dragapult", "dragapult" in available_decks(tmp))
check("deck_csv_path works",
      os.path.normpath(deck_csv_path("dragapult", tmp)) == os.path.normpath(os.path.join(mock_deck, "deck.csv")))
check("agent_main_path works",
      os.path.normpath(agent_main_path("dragapult", tmp)) == os.path.normpath(os.path.join(mock_deck, "main.py")))
check("lucario_v3 still None", resolve_deck_dir("lucario_v3", tmp) is None)

shutil.rmtree(tmp)

print("\n=== setup_agents.py --help ===")
setup_path = os.path.join(os.path.dirname(__file__), "web", "setup_agents.py")
r = subprocess.run([sys.executable, setup_path, "--help"], capture_output=True, text=True)
check("setup_agents --help exits 0", r.returncode == 0)
check("setup_agents --help shows usage", "usage" in r.stdout.lower() or "download" in r.stdout.lower())

print("\n=== run_with_deck.py --list ===")
rwd_path = os.path.join(os.path.dirname(__file__), "web", "run_with_deck.py")
r2 = subprocess.run([sys.executable, rwd_path, "--list"], capture_output=True, text=True)
check("run_with_deck --list exits cleanly", r2.returncode == 0)
check("--list shows Available", "Available" in r2.stdout or "available" in r2.stdout.lower())

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
