"""
Run self-play with an external agent's main.py and deck.

Loads the external agent as a module, runs games via cg.game,
and saves per-game results CSV + basic action logs.

Usage:
  python experiments/run_external_agent.py \
      --agent experiments/agents/top_lucario_1084_main.py \
      --deck experiments/decks/top_lucario_1084.csv \
      --n 50 --start-game 316000 \
      --output artifacts/top_lucario_1084_results.csv
"""
from __future__ import annotations
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from collections import defaultdict

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))


def load_agent_module(path: str):
    spec = importlib.util.spec_from_file_location("external_agent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_deck(path: str) -> list[int]:
    cards = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cards.append(int(line))
    return cards


def main():
    parser = argparse.ArgumentParser(description="Run external agent self-play")
    parser.add_argument("--agent", required=True, help="Path to agent main.py")
    parser.add_argument("--deck", required=True, help="Path to deck CSV")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--start-game", type=int, default=316000)
    parser.add_argument("--output", default="artifacts/external_agent_results.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate args and create output dir without running games")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    if args.dry_run:
        dry = {"mode": "dry_run", "agent": args.agent, "deck": args.deck,
               "n": args.n, "output": args.output}
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(dry) + "\n")
        print("Dry run: validated args, created %s" % args.output)
        return

    if sys.platform == "win32":
        print("ERROR: This script must run inside WSL (libcg.so is Linux only).")
        print("Use: wsl python experiments/run_external_agent.py ...")
        sys.exit(1)

    print(f"Loading agent from {args.agent}...")
    agent_mod = load_agent_module(args.agent)
    agent_fn = agent_mod.agent

    deck = load_deck(args.deck)
    print(f"Deck: {len(deck)} cards from {args.deck}")

    from cg.api import to_observation_class
    from cg.game import battle_finish, battle_select, battle_start

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    results = []
    action_counts = defaultdict(int)
    total_decisions = 0

    for gi in range(args.n):
        gid = args.start_game + gi
        obs = None
        try:
            obs, start_data = battle_start(deck, deck)
            if obs is None:
                results.append({"game": gid, "game_id": gid, "winner": "error", "turns": 0, "error": "start_failed", "returncode": 1})
                continue

            for step in range(2000):
                obc = to_observation_class(obs)
                if obc.current.result >= 0:
                    winner = "p0" if obc.current.result == 0 else "p1" if obc.current.result == 1 else "draw"
                    results.append({"game": gid, "game_id": gid, "winner": winner, "turns": obc.current.turn, "error": "", "returncode": 0})
                    break

                sel = obc.select
                if sel and sel.option and len(sel.option) > 1:
                    total_decisions += 1
                    chosen = agent_fn(obs)
                    if chosen and sel.option:
                        idx = chosen[0] if isinstance(chosen, list) else chosen
                        if idx < len(sel.option):
                            otype = sel.option[idx].type
                            action_counts[int(otype)] = action_counts.get(int(otype), 0) + 1
                else:
                    chosen = agent_fn(obs)

                obs = battle_select(chosen)
            else:
                results.append({"game": gid, "game_id": gid, "winner": "timeout", "turns": 2000, "error": "max_steps", "returncode": -1})
        except Exception as ex:
            results.append({"game": gid, "game_id": gid, "winner": "error", "turns": 0, "error": str(ex)[:100], "returncode": 1})
        finally:
            if obs is not None:
                try:
                    battle_finish()
                except Exception:
                    pass

        if (gi + 1) % 10 == 0:
            wins = sum(1 for r in results if r["winner"] == "p0")
            print(f"  {gi+1}/{args.n} games, p0 wins: {wins}")

    with open(args.output, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    wins = sum(1 for r in results if r["winner"] == "p0")
    losses = sum(1 for r in results if r["winner"] == "p1")
    errors = sum(1 for r in results if r["winner"] == "error")
    timeouts = sum(1 for r in results if r["winner"] == "timeout")

    _NAMES = {0: "NUMBER", 1: "YES", 3: "CARD", 7: "PLAY", 8: "ATTACH",
              9: "EVOLVE", 10: "ABILITY", 12: "RETREAT", 13: "ATTACK", 14: "END", 15: "SKILL"}
    print(f"\nResults ({len(results)} games):")
    print(f"  p0 wins: {wins}, p1 wins: {losses}, errors: {errors}, timeouts: {timeouts}")
    print(f"  Total decisions: {total_decisions}")
    print(f"  Action distribution:")
    for k, v in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"    {_NAMES.get(k, k)}: {v} ({v/total_decisions*100:.1f}%)" if total_decisions else f"    {k}: {v}")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
