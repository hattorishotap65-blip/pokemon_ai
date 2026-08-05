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
import json
import os
import sys
import time

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
    parser.add_argument("--first-player", choices=("a", "b"), default="a",
                        help="Which of agent-a/agent-b occupies seat 0 when gi%%2==0. "
                             "Default 'a' preserves pre-existing behavior exactly (controls "
                             "player-index/deck slot only, not engine-level move order).")
    parser.add_argument("--jsonl-out", default="",
                        help="Optional: append one JSON record per game to this path. "
                             "When unset (default), no per-game instrumentation runs and "
                             "existing behavior/output is unchanged.")
    parser.add_argument("--record-decision-timing", action="store_true",
                        help="Only meaningful together with --jsonl-out. Records a wall-clock "
                             "duration_ms per candidate decision inside each game record.")
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
    first_is_a = (args.first_player == "a")
    jsonl_f = open(args.jsonl_out, "a", encoding="utf-8") if args.jsonl_out else None

    try:
        for gi in range(args.n):
            # With the default --first-player a, a_first_this_game == (gi % 2 == 0) for
            # every gi, i.e. algebraically identical to the original `if gi % 2 == 0:` branch.
            a_first_this_game = first_is_a if gi % 2 == 0 else not first_is_a
            if a_first_this_game:
                d0, d1 = deck_a, deck_b
                ag0, ag1 = agent_a, agent_b
                a_idx = 0
            else:
                d0, d1 = deck_b, deck_a
                ag0, ag1 = agent_b, agent_a
                a_idx = 1

            record = None
            if jsonl_f is not None:
                record = {
                    "schema_version": "1",
                    "game_index": gi,
                    "first_seat_agent": "a" if a_first_this_game else "b",
                    "label_a": args.label_a,
                    "label_b": args.label_b,
                    "termination": None,
                    "result": None,
                    "error_actor": None,
                    "legality": "unknown",
                    "decisions": [] if args.record_decision_timing else None,
                }

            obs = None
            try:
                obs, sd = battle_start(d0, d1)
                if obs is None:
                    errors += 1
                    if record is not None:
                        record["termination"] = {"category": "error", "kind": "engine_null_start"}
                    continue
                for step in range(2000):
                    obc = to_observation_class(obs)
                    if obc.current.result >= 0:
                        if obc.current.result == a_idx:
                            a_wins += 1
                            if record is not None:
                                record["termination"] = {"category": "result", "kind": "win"}
                                record["result"] = {"winner": "a"}
                        elif obc.current.result == (1 - a_idx):
                            b_wins += 1
                            if record is not None:
                                record["termination"] = {"category": "result", "kind": "win"}
                                record["result"] = {"winner": "b"}
                        else:
                            draws += 1
                            if record is not None:
                                record["termination"] = {"category": "result", "kind": "draw"}
                                record["result"] = {"winner": "draw"}
                        if record is not None:
                            record["legality"] = "legal"
                        break
                    active = ag0 if obc.current.yourIndex == 0 else ag1
                    if jsonl_f is not None:
                        active_is_a = (active is agent_a)
                        t0 = time.perf_counter() if args.record_decision_timing else None
                        try:
                            action = active(obs)
                        except Exception:
                            record["error_actor"] = "a" if active_is_a else "b"
                            raise
                        if t0 is not None:
                            # "actor" distinguishes which agent (a or b) made this decision --
                            # a game's decisions come from BOTH agents (turns alternate), so a
                            # consumer computing decision-time/observation-count for just one
                            # arm must filter on this field, not assume every entry belongs to
                            # whichever agent is being evaluated.
                            record["decisions"].append({
                                "ply": step, "actor": "a" if active_is_a else "b",
                                "duration_ms": round((time.perf_counter() - t0) * 1000, 3),
                            })
                        try:
                            obs = battle_select(action)
                        except IndexError:
                            # Per cg/game.py's own contract: any battle_select err != 0 and
                            # err != 30 raises a bare IndexError. err == 30 ("battle_ptr
                            # broken") raises ValueError instead and is NOT reclassified here
                            # -- see README.md caveat F2 for the one known misattribution gap
                            # (a malformed agent return also raises ValueError, before this
                            # point, and is attributed to "engine" rather than the agent).
                            record["error_actor"] = "a" if active_is_a else "b"
                            record["legality"] = "illegal"
                            raise
                        except Exception:
                            record["error_actor"] = "engine"
                            raise
                    else:
                        obs = battle_select(active(obs))
                else:
                    timeouts += 1
                    if record is not None:
                        record["termination"] = {"category": "timeout", "kind": "step_limit"}
            except Exception as ex:
                errors += 1
                if record is not None and record["termination"] is None:
                    if record["legality"] == "illegal":
                        kind = "illegal_action"
                    elif record["error_actor"] in ("a", "b"):
                        kind = "agent_exception"
                    elif record["error_actor"] == "engine":
                        kind = "engine_ptr_broken"
                    else:
                        kind = "unclassified_exception"
                    record["termination"] = {"category": "error", "kind": kind}
            finally:
                if obs is not None:
                    try:
                        battle_finish()
                    except Exception:
                        pass
                if record is not None:
                    jsonl_f.write(json.dumps(record) + "\n")

            if (gi + 1) % 20 == 0:
                print(f"  {gi+1}/{args.n}: {args.label_a} {a_wins} - {args.label_b} {b_wins}")
    finally:
        if jsonl_f is not None:
            jsonl_f.close()

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
