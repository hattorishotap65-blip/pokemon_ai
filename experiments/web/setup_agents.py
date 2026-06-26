"""Download and set up agent decks for the web sandbox.

Usage (from WSL or any shell):
    python3 experiments/web/setup_agents.py

Clones wmh/ptcg-abc (shallow) and copies agents/ into experiments/web/agents/.
Skips if agents/ already exists with at least one deck.
"""
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(SCRIPT_DIR, "agents")


def _has_agents():
    if not os.path.isdir(AGENTS_DIR):
        return False
    for name in os.listdir(AGENTS_DIR):
        d = os.path.join(AGENTS_DIR, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "deck.csv")):
            return True
    return False


def main():
    if _has_agents():
        count = sum(
            1 for n in os.listdir(AGENTS_DIR)
            if os.path.isdir(os.path.join(AGENTS_DIR, n))
            and os.path.exists(os.path.join(AGENTS_DIR, n, "deck.csv"))
        )
        print("[setup] agents/ already exists with %d decks, skipping." % count)
        print("[setup] To re-download, delete %s and run again." % AGENTS_DIR)
        return

    print("[setup] Cloning wmh/ptcg-abc (shallow)...")
    tmp = tempfile.mkdtemp()
    try:
        r = subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/wmh/ptcg-abc.git", tmp],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print("[setup] git clone failed: %s" % r.stderr[:200])
            sys.exit(1)

        src = os.path.join(tmp, "agents")
        if not os.path.isdir(src):
            print("[setup] ERROR: agents/ not found in ptcg-abc repo")
            sys.exit(1)

        shutil.copytree(src, AGENTS_DIR)

        count = sum(
            1 for n in os.listdir(AGENTS_DIR)
            if os.path.isdir(os.path.join(AGENTS_DIR, n))
            and os.path.exists(os.path.join(AGENTS_DIR, n, "deck.csv"))
        )
        print("[setup] Copied %d agent decks to %s" % (count, AGENTS_DIR))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download agent decks for web sandbox")
    parser.parse_args()
    main()
