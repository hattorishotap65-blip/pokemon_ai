"""Run trace evaluation using a web sandbox deck.

Bridges web sandbox deck registry with experiments/learning/run_cabt_trace_eval.py.

Usage (from WSL):
    python3 experiments/web/run_with_deck.py --deck lucario_v3 --n 10 --skip-command
    python3 experiments/web/run_with_deck.py --deck dragapult --n 50 --use-advisor
    python3 experiments/web/run_with_deck.py --list  # show available decks

Finds agent main.py and deck.csv from the web sandbox deck registry,
then delegates to run_cabt_trace_eval.py.
"""
import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, SCRIPT_DIR)

from deck_registry import DECKS, available_decks, deck_csv_path, agent_main_path


def main():
    parser = argparse.ArgumentParser(description="Run trace eval with a web sandbox deck")
    parser.add_argument("--deck", default="", help="Deck name from registry")
    parser.add_argument("--list", action="store_true", help="List available decks and exit")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--use-advisor", action="store_true")
    parser.add_argument("--skip-command", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--label", default="")
    parser.add_argument("--weights", default="", help="Path to learned weights JSON")
    parser.add_argument("--fallback-weights", default="", help="Path to fallback weights JSON")
    args = parser.parse_args()

    avail = available_decks(SCRIPT_DIR)

    if args.list:
        print("Available decks (%d):" % len(avail))
        for name in avail:
            dc = deck_csv_path(name, SCRIPT_DIR)
            ag = agent_main_path(name, SCRIPT_DIR)
            print("  %-20s deck=%s agent=%s" % (name, dc, ag))
        if not avail:
            print("  (none — run setup_agents.py first)")
        return

    if not avail:
        print("No decks available. Run: python3 experiments/web/setup_agents.py")
        sys.exit(1)

    deck_name = args.deck if args.deck in avail else avail[0]
    deck_path = deck_csv_path(deck_name, SCRIPT_DIR)
    agent_path = agent_main_path(deck_name, SCRIPT_DIR)

    print("[run_with_deck] deck=%s agent=%s deck_csv=%s" % (deck_name, agent_path, deck_path))

    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "experiments", "learning", "run_cabt_trace_eval.py"),
        "--agent", agent_path,
        "--deck", deck_path,
        "--n", str(args.n),
    ]
    if args.use_advisor:
        cmd.append("--use-advisor")
    if args.skip_command or args.dry_run:
        cmd.append("--skip-command")
    if args.run_dir:
        cmd.extend(["--run-dir", args.run_dir])
    if args.label:
        cmd.extend(["--label", args.label])
    if args.weights:
        cmd.extend(["--weights", args.weights])
    if args.fallback_weights:
        cmd.extend(["--fallback-weights", args.fallback_weights])

    print("[run_with_deck] command: %s" % " ".join(cmd))
    r = subprocess.run(cmd)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
