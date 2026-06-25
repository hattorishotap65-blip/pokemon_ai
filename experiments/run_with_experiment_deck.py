"""
Run self-play with an experiment deck, then restore the original deck.csv.

Temporarily replaces deck.csv, runs action_feature_logging, then restores.
Always restores even on error.

Usage:
  python experiments/run_with_experiment_deck.py \
      --deck experiments/decks/top_crustle_replay.csv \
      --n 50 --start-game 310000 \
      --output artifacts/top_crustle_replay_50g.jsonl
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DECK_CSV = os.path.join(_REPO_ROOT, "deck.csv")
_BACKUP = os.path.join(_REPO_ROOT, "deck.csv.bak")


def main():
    parser = argparse.ArgumentParser(
        description="Run self-play with experiment deck"
    )
    parser.add_argument("--deck", required=True, help="Experiment deck CSV path")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--start-game", type=int, default=310000)
    parser.add_argument("--output", default="artifacts/experiment_deck.jsonl")
    parser.add_argument("--use-wsl", action="store_true", default=True)
    args = parser.parse_args()

    if not os.path.exists(args.deck):
        print(f"ERROR: deck file not found: {args.deck}")
        sys.exit(1)

    with open(args.deck) as f:
        lines = [l.strip() for l in f if l.strip()]
    if len(lines) != 60:
        print(f"ERROR: deck has {len(lines)} cards, expected 60")
        sys.exit(1)

    print(f"Experiment deck: {args.deck} ({len(lines)} cards)")
    print(f"Backing up {_DECK_CSV} -> {_BACKUP}")
    shutil.copy2(_DECK_CSV, _BACKUP)

    try:
        print(f"Replacing deck.csv with experiment deck...")
        shutil.copy2(args.deck, _DECK_CSV)

        cmd = [
            sys.executable, "experiments/action_feature_logging.py",
            "--n", str(args.n),
            "--start-game", str(args.start_game),
            "--run-games", "--use-wsl",
            "--output", args.output,
        ]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=_REPO_ROOT, timeout=600)

        if result.returncode != 0:
            print(f"WARNING: action_feature_logging exited with {result.returncode}")
    except subprocess.TimeoutExpired:
        print("WARNING: execution timed out")
    except Exception as ex:
        print(f"ERROR: {ex}")
    finally:
        print(f"Restoring {_BACKUP} -> {_DECK_CSV}")
        if os.path.exists(_BACKUP):
            shutil.copy2(_BACKUP, _DECK_CSV)
            os.remove(_BACKUP)
            print("Restored successfully")
        else:
            print("WARNING: backup not found, deck.csv may be corrupted!")


if __name__ == "__main__":
    main()
