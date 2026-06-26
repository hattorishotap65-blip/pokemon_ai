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

print("\n=== CLI --help ===")

r_help1 = subprocess.run([sys.executable, path_rea, "--help"], capture_output=True, text=True)
check("run_external_agent --help succeeds", r_help1.returncode == 0)

r_help2 = subprocess.run([sys.executable, path_hth, "--help"], capture_output=True, text=True)
check("head_to_head --help succeeds", r_help2.returncode == 0)

print("\n=== --dry-run ===")

import tempfile
tmp_dir = tempfile.mkdtemp()

dry_out1 = os.path.join(tmp_dir, "dry_rea.jsonl")
r_dry1 = subprocess.run([
    sys.executable, path_rea, "--agent", "main.py", "--deck", "deck.csv",
    "--dry-run", "--output", dry_out1,
], capture_output=True, text=True)
check("run_external_agent --dry-run succeeds", r_dry1.returncode == 0)
check("run_external_agent --dry-run creates file", os.path.exists(dry_out1))

dry_out2 = os.path.join(tmp_dir, "dry_hth.json")
r_dry2 = subprocess.run([
    sys.executable, path_hth, "--agent-a", "main.py", "--deck-a", "deck.csv",
    "--agent-b", "main.py", "--deck-b", "deck.csv",
    "--dry-run", "--output", dry_out2,
], capture_output=True, text=True)
check("head_to_head --dry-run succeeds", r_dry2.returncode == 0)
check("head_to_head --dry-run creates file", os.path.exists(dry_out2))

import shutil
shutil.rmtree(tmp_dir, ignore_errors=True)

print("\n=== deck files ===")

for deck_name in ["top_crustle_replay.csv", "raging_bolt_ogerpon.csv"]:
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
