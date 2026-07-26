"""
Loss pattern analysis: Raging Bolt vs Lucario.

Runs N games and collects per-game stats:
  - first attack turn for each side
  - attack usage counts (Bellowing Thunder / Myriad Leaf Shower / Burst Roar)
  - prize race timeline (turn at which each side took each prize)
  - game length, result
  - loss classification

Usage (inside WSL):
  python3 experiments/analyze_lucario_losses.py --n 100 --output /tmp/lucario_loss_analysis.json
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys
from collections import Counter

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))

BELLOWING_THUNDER = 72
MYRIAD_LEAF_SHOWER = 120
BURST_ROAR = 71


def load_agent(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def load_deck(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [int(l.strip()) for l in f if l.strip()]


def classify_loss(g):
    """Classify why Bolt lost this game."""
    if g["bolt_first_attack_turn"] is None:
        return "never_attacked"
    if g["bolt_prizes_taken"] == 0:
        return "shutout"           # attacked but took no prizes
    if g["bolt_prizes_taken"] <= 2:
        return "outpaced_early"    # took 1-2, lost the race badly
    return "outpaced_close"        # took 3+, close race


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if sys.platform == "win32":
        print("ERROR: Run inside WSL (libcg.so is Linux only).")
        sys.exit(1)

    bolt_agent = load_agent(os.path.join(_REPO_ROOT, "experiments/agents/raging_bolt/main.py"), "bolt")
    bolt_deck = load_deck(os.path.join(_REPO_ROOT, "experiments/decks/raging_bolt_ogerpon.csv"))
    luc_agent = load_agent(os.path.join(_REPO_ROOT, "experiments/agents/top_lucario_1084_main.py"), "lucario")
    luc_deck = load_deck(os.path.join(_REPO_ROOT, "experiments/decks/top_lucario_1084.csv"))

    from cg.api import to_observation_class, OptionType
    from cg.game import battle_finish, battle_select, battle_start

    games = []

    for gi in range(args.n):
        if gi % 2 == 0:
            d0, d1 = bolt_deck, luc_deck
            ag0, ag1 = bolt_agent, luc_agent
            bolt_idx = 0
        else:
            d0, d1 = luc_deck, bolt_deck
            ag0, ag1 = luc_agent, bolt_agent
            bolt_idx = 1

        g = {
            "game": gi,
            "bolt_index": bolt_idx,
            "bolt_first": (bolt_idx == 0),  # provisional; updated by IS_FIRST outcome via turn order
            "result": None,
            "turns": 0,
            "bolt_first_attack_turn": None,
            "luc_first_attack_turn": None,
            "bolt_attacks": Counter(),
            "bolt_attack_turns": 0,   # number of turns bolt attacked
            "luc_attack_turns": 0,
            "bolt_prize_timeline": [],  # turn at which bolt took each prize
            "luc_prize_timeline": [],
            "bolt_prizes_taken": 0,
            "luc_prizes_taken": 0,
        }

        obs = None
        prev_prizes = [0, 0]  # prizes remaining per player index (0 until dealt)
        try:
            obs, sd = battle_start(d0, d1)
            if obs is None:
                continue
            for step in range(2000):
                obc = to_observation_class(obs)
                st = obc.current
                g["turns"] = st.turn

                # players[i].prize = prizes REMAINING for player i to take.
                # Starts empty, becomes 6 after setup, shrinks as player i takes prizes.
                for pi in (0, 1):
                    cur = len(st.players[pi].prize)
                    if cur > prev_prizes[pi]:
                        prev_prizes[pi] = cur  # prizes dealt at setup
                    elif cur < prev_prizes[pi]:
                        n_taken = prev_prizes[pi] - cur
                        who = "bolt" if pi == bolt_idx else "luc"
                        for _ in range(n_taken):
                            g[f"{who}_prize_timeline"].append(st.turn)
                        prev_prizes[pi] = cur

                if st.result >= 0:
                    g["result"] = "win" if st.result == bolt_idx else (
                        "loss" if st.result == (1 - bolt_idx) else "draw")
                    break

                is_bolt_turn = (st.yourIndex == bolt_idx)
                active_agent = ag0 if st.yourIndex == 0 else ag1
                picks = active_agent(obs)

                # attack detection
                if obc.select and obc.select.option and picks:
                    for idx in picks:
                        if idx < len(obc.select.option):
                            o = obc.select.option[idx]
                            if o.type == OptionType.ATTACK:
                                if is_bolt_turn:
                                    if g["bolt_first_attack_turn"] is None:
                                        g["bolt_first_attack_turn"] = st.turn
                                    g["bolt_attacks"][o.attackId] += 1
                                    g["bolt_attack_turns"] += 1
                                else:
                                    if g["luc_first_attack_turn"] is None:
                                        g["luc_first_attack_turn"] = st.turn
                                    g["luc_attack_turns"] += 1

                obs = battle_select(picks)
            else:
                g["result"] = "timeout"
        except Exception as ex:
            g["result"] = f"error: {ex}"
        finally:
            if obs is not None:
                try:
                    battle_finish()
                except Exception:
                    pass

        g["bolt_prizes_taken"] = len(g["bolt_prize_timeline"])
        g["luc_prizes_taken"] = len(g["luc_prize_timeline"])
        g["bolt_attacks"] = dict(g["bolt_attacks"])
        games.append(g)

        if (gi + 1) % 20 == 0:
            w = sum(1 for x in games if x["result"] == "win")
            print(f"  {gi+1}/{args.n}: bolt wins {w}")

    # ── Aggregate ──
    wins = [g for g in games if g["result"] == "win"]
    losses = [g for g in games if g["result"] == "loss"]

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 2) if xs else None

    print(f"\n=== BOLT vs LUCARIO loss analysis ({len(games)}g) ===")
    print(f"wins: {len(wins)}  losses: {len(losses)}  other: {len(games)-len(wins)-len(losses)}")

    print("\n-- Speed --")
    print(f"bolt first attack turn: avg {avg([g['bolt_first_attack_turn'] for g in games])}")
    print(f"luc  first attack turn: avg {avg([g['luc_first_attack_turn'] for g in games])}")
    never = sum(1 for g in games if g["bolt_first_attack_turn"] is None)
    print(f"bolt never attacked: {never}/{len(games)}")

    print("\n-- Attack usage (all games) --")
    total_attacks = Counter()
    for g in games:
        for aid, n in g["bolt_attacks"].items():
            total_attacks[int(aid)] += n
    name = {BELLOWING_THUNDER: "BellowingThunder", MYRIAD_LEAF_SHOWER: "MyriadLeafShower", BURST_ROAR: "BurstRoar"}
    for aid, n in total_attacks.most_common():
        print(f"  {name.get(aid, aid)}: {n}")

    print("\n-- Attack cadence --")
    print(f"bolt attack turns per game: avg {avg([g['bolt_attack_turns'] for g in games])}")
    print(f"luc  attack turns per game: avg {avg([g['luc_attack_turns'] for g in games])}")
    print(f"avg game length (turns): {avg([g['turns'] for g in games])}")

    print("\n-- Prize race (losses only) --")
    print(f"bolt prizes taken in losses: avg {avg([g['bolt_prizes_taken'] for g in losses])}")
    dist = Counter(g["bolt_prizes_taken"] for g in losses)
    for k in sorted(dist):
        print(f"  took {k} prizes: {dist[k]} games")

    print("\n-- Loss classification --")
    cls = Counter(classify_loss(g) for g in losses)
    for k, v in cls.most_common():
        print(f"  {k}: {v}")

    print("\n-- Prize timeline (avg turn each prize taken, losses) --")
    for who in ("luc", "bolt"):
        rows = []
        for prize_i in range(6):
            turns = [g[f"{who}_prize_timeline"][prize_i] for g in losses
                     if len(g[f"{who}_prize_timeline"]) > prize_i]
            rows.append(f"P{prize_i+1}:{avg(turns)}({len(turns)})")
        print(f"  {who}: " + "  ".join(rows))

    print("\n-- First-player effect --")
    for first in (True, False):
        sub = [g for g in games if (g["bolt_index"] == 0) == first]
        w = sum(1 for g in sub if g["result"] == "win")
        print(f"  bolt as P{'0' if first else '1'}: {w}/{len(sub)} wins")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(games, f, ensure_ascii=False, indent=1, default=str)
        print(f"\nSaved raw data to {args.output}")


if __name__ == "__main__":
    main()
