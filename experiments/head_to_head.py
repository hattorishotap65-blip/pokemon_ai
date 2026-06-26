"""
Head-to-head match between two agents with different decks.

Usage (inside WSL):
  python experiments/head_to_head.py \
      --agent-a main.py --deck-a deck.csv \
      --agent-b experiments/agents/top_lucario_1084_main.py \
      --deck-b experiments/decks/top_lucario_1084.csv \
      --n 100
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))


def load_agent(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def load_deck(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [int(l.strip()) for l in f if l.strip()]


def main():
    parser = argparse.ArgumentParser(description="Head-to-head agent match")
    parser.add_argument("--agent-a", required=True)
    parser.add_argument("--deck-a", required=True)
    parser.add_argument("--agent-b", required=True)
    parser.add_argument("--deck-b", required=True)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--output", default="", help="Save summary JSON to this path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate args and create output without running games")
    args = parser.parse_args()

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    if args.dry_run:
        import json
        dry = {"mode": "dry_run", "agent_a": args.agent_a, "agent_b": args.agent_b,
               "deck_a": args.deck_a, "deck_b": args.deck_b, "n": args.n}
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(dry, f, indent=2)
        print("Dry run: validated args")
        if args.output:
            print("Created %s" % args.output)
        return

    if sys.platform == "win32":
        print("ERROR: Run inside WSL (libcg.so is Linux only).")
        sys.exit(1)

    print(f"Loading {args.label_a}: {args.agent_a} + {args.deck_a}")
    agent_a = load_agent(args.agent_a, "agent_a")
    deck_a = load_deck(args.deck_a)

    print(f"Loading {args.label_b}: {args.agent_b} + {args.deck_b}")
    agent_b = load_agent(args.agent_b, "agent_b")
    deck_b = load_deck(args.deck_b)

    from cg.api import to_observation_class
    from cg.game import battle_finish, battle_select, battle_start

    a_wins = b_wins = draws = errors = timeouts = 0

    for gi in range(args.n):
        if gi % 2 == 0:
            d0, d1 = deck_a, deck_b
            ag0, ag1 = agent_a, agent_b
            a_idx = 0
        else:
            d0, d1 = deck_b, deck_a
            ag0, ag1 = agent_b, agent_a
            a_idx = 1

        obs = None
        try:
            obs, sd = battle_start(d0, d1)
            if obs is None:
                errors += 1
                continue
            for step in range(2000):
                obc = to_observation_class(obs)
                if obc.current.result >= 0:
                    if obc.current.result == a_idx:
                        a_wins += 1
                    elif obc.current.result == (1 - a_idx):
                        b_wins += 1
                    else:
                        draws += 1
                    break
                active = ag0 if obc.current.yourIndex == 0 else ag1
                obs = battle_select(active(obs))
            else:
                timeouts += 1
        except Exception as ex:
            errors += 1
        finally:
            if obs is not None:
                try:
                    battle_finish()
                except Exception:
                    pass

        if (gi + 1) % 20 == 0:
            print(f"  {gi+1}/{args.n}: {args.label_a} {a_wins} - {args.label_b} {b_wins}")

    total = a_wins + b_wins
    print(f"\n=== {args.label_a} vs {args.label_b} ({args.n}g) ===")
    print(f"{args.label_a} wins: {a_wins}")
    print(f"{args.label_b} wins: {b_wins}")
    print(f"Draws: {draws}")
    print(f"Errors: {errors}")
    print(f"Timeouts: {timeouts}")
    if total > 0:
        print(f"{args.label_a} win rate: {a_wins/total*100:.1f}%")

    if args.output:
        import json
        summary = {
            "games": args.n, "agent_a_wins": a_wins, "agent_b_wins": b_wins,
            "draws": draws, "errors": errors, "timeouts": timeouts,
            "label_a": args.label_a, "label_b": args.label_b,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Saved summary to {args.output}")


if __name__ == "__main__":
    main()
