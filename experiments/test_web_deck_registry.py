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
for name, (display, path) in DECKS.items():
    check("%s display is string" % name, isinstance(display, str) and len(display) > 0)
    check("%s path is valid spec" % name, path.startswith("agents/") or path == "@@PROJECT_ROOT")

print("\n=== my_deck (project root) ===")
check("my_deck in DECKS", "my_deck" in DECKS)
my_dir = resolve_deck_dir("my_deck")
check("my_deck resolves", my_dir is not None)
if my_dir:
    check("my_deck has deck.csv", os.path.exists(os.path.join(my_dir, "deck.csv")))
    check("my_deck has main.py", os.path.exists(os.path.join(my_dir, "main.py")))

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
check("setup_agents exits 0", r.returncode == 0 or "usage" in r.stdout.lower() or "setup" in r.stderr.lower())

print("\n=== run_with_deck.py --list ===")
rwd_path = os.path.join(os.path.dirname(__file__), "web", "run_with_deck.py")
r2 = subprocess.run([sys.executable, rwd_path, "--list"], capture_output=True, text=True)
check("run_with_deck --list exits cleanly", r2.returncode == 0)
check("--list shows Available", "Available" in r2.stdout or "available" in r2.stdout.lower())

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
