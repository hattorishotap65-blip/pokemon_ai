"""
Tests for experiments/run_external_agent.py and experiments/head_to_head.py.

Verifies module structure and CLI argument parsing without running
actual games (cg.game requires WSL/Linux).

Run: python experiments/test_cabt_runner_scripts.py
"""
import importlib.util
import os
import subprocess
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


print("=== run_external_agent.py ===")

path_rea = os.path.join(os.path.dirname(__file__), "run_external_agent.py")
check("file exists", os.path.exists(path_rea))

result = subprocess.run(
    [sys.executable, "-m", "py_compile", path_rea],
    capture_output=True, text=True
)
check("compiles", result.returncode == 0)

# Check it has main() and load_agent/load_deck
with open(path_rea, encoding="utf-8") as f:
    content = f.read()
check("has main()", "def main()" in content)
check("has load_agent", "load_agent" in content)
check("has load_deck()", "def load_deck(" in content)
check("has --agent arg", "--agent" in content)
check("has --deck arg", "--deck" in content)
check("has --n arg", '"--n"' in content)
check("has --output arg", "--output" in content)
check("has platform guard", "win32" in content)

print("\n=== head_to_head.py ===")

path_hth = os.path.join(os.path.dirname(__file__), "head_to_head.py")
check("file exists", os.path.exists(path_hth))

result2 = subprocess.run(
    [sys.executable, "-m", "py_compile", path_hth],
    capture_output=True, text=True
)
check("compiles", result2.returncode == 0)

with open(path_hth, encoding="utf-8") as f:
    content2 = f.read()
check("has main()", "def main()" in content2)
check("has load_agent", "load_agent" in content2)
check("has load_deck()", "def load_deck(" in content2)
check("has --agent-a arg", "--agent-a" in content2)
check("has --agent-b arg", "--agent-b" in content2)
check("has --deck-a arg", "--deck-a" in content2)
check("has --deck-b arg", "--deck-b" in content2)
check("has --n arg", '"--n"' in content2)
check("has platform guard", "win32" in content2)

print("\n=== run_with_experiment_deck.py ===")

path_rwed = os.path.join(os.path.dirname(__file__), "run_with_experiment_deck.py")
check("file exists", os.path.exists(path_rwed))

result3 = subprocess.run(
    [sys.executable, "-m", "py_compile", path_rwed],
    capture_output=True, text=True
)
check("compiles", result3.returncode == 0)

print("\n=== deck files ===")

for deck_name in ["top_lucario_1084.csv", "top_crustle_replay.csv", "raging_bolt_ogerpon.csv"]:
    deck_path = os.path.join(os.path.dirname(__file__), "decks", deck_name)
    exists = os.path.exists(deck_path)
    if exists:
        with open(deck_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        check("%s exists and has 60 cards" % deck_name, len(lines) == 60)
    else:
        check("%s exists" % deck_name, False)

print("\n%d/%d passed" % (_total - _failures, _total))
if _failures:
    sys.exit(1)
