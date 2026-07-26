"""
Deck-usage analysis for deck-construction review.

Runs N games vs Lucario and, for each LOSS, records what was stranded:
  - key cards still unseen (deck+prizes) at game end
  - dead cards in hand at game end
  - attack cadence stats

Usage (inside WSL):
  python3 experiments/analyze_deck_usage.py --n 100
"""
from __future__ import annotations
import argparse
import os
import sys
from collections import Counter

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))

import importlib.util


def load_agent(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


KEY_NAMES = {
    63: "RagingBolt", 96: "Ogerpon",
    1: "GrassE", 4: "LightningE", 6: "FightingE",
    1198: "Crispin", 1227: "Lillie", 1182: "Boss",
    1118: "EnergyRetrieval", 1094: "BugCatchingSet", 1127: "TeraOrb",
    1121: "UltraBall", 1122: "Pokegear", 1124: "Catcher", 1123: "Switch",
    1080: "UnfairStamp",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()

    if sys.platform == "win32":
        print("ERROR: run in WSL"); sys.exit(1)

    bolt_mod = load_agent(os.path.join(_REPO_ROOT, "experiments/agents/raging_bolt/main.py"), "bolt")
    bolt_agent, bolt_deck = bolt_mod.agent, bolt_mod.my_deck
    luc_mod = load_agent(os.path.join(_REPO_ROOT, "experiments/agents/top_lucario_1084_main.py"), "luc")
    luc_agent = luc_mod.agent
    luc_deck = [int(l) for l in open(os.path.join(_REPO_ROOT, "experiments/decks/top_lucario_1084.csv")) if l.strip()]

    from cg.api import to_observation_class, OptionType
    from cg.game import battle_finish, battle_select, battle_start

    full = Counter(bolt_deck)
    losses = 0; wins = 0
    unseen_at_loss = Counter()   # cards stuck in deck+prizes at loss
    hand_at_loss = Counter()     # dead cards in hand at loss
    attack_turn_counts = []

    for gi in range(args.n):
        if gi % 2 == 0:
            d0, d1, ag0, ag1, bolt_idx = bolt_deck, luc_deck, bolt_agent, luc_agent, 0
        else:
            d0, d1, ag0, ag1, bolt_idx = luc_deck, bolt_deck, luc_agent, bolt_agent, 1

        obs = None
        result = None
        attacks = 0
        last_obc = None
        try:
            obs, sd = battle_start(d0, d1)
            if obs is None:
                continue
            for step in range(2000):
                obc = to_observation_class(obs)
                if obc.current.result >= 0:
                    result = "win" if obc.current.result == bolt_idx else "loss"
                    last_obc = obc
                    break
                is_bolt = (obc.current.yourIndex == bolt_idx)
                picks = (ag0 if obc.current.yourIndex == 0 else ag1)(obs)
                if is_bolt and obc.select and obc.select.option:
                    for idx in picks:
                        if idx < len(obc.select.option) and obc.select.option[idx].type == OptionType.ATTACK:
                            attacks += 1
                obs = battle_select(picks)
                last_obc = obc
        except Exception:
            result = None
        finally:
            if obs is not None:
                try:
                    battle_finish()
                except Exception:
                    pass

        if result == "win":
            wins += 1
        if result != "loss" or last_obc is None:
            continue
        losses += 1
        attack_turn_counts.append(attacks)

        me = last_obc.current.players[bolt_idx]
        seen = Counter()
        for c in (me.hand or []):
            seen[c.id] += 1
            hand_at_loss[c.id] += 1
        for c in (me.discard or []):
            seen[c.id] += 1
        for pk in list(me.active or []) + list(me.bench or []):
            if not pk:
                continue
            seen[pk.id] += 1
            for c in (pk.energyCards or []):
                seen[c.id] += 1
            for c in (pk.tools or []):
                seen[c.id] += 1
            for c in (pk.preEvolution or []):
                seen[c.id] += 1
        for cid, cnt in full.items():
            stuck = cnt - seen.get(cid, 0)
            if stuck > 0:
                unseen_at_loss[cid] += stuck

    def nm(cid):
        return KEY_NAMES.get(cid, f"#{cid}")

    print(f"\n=== Deck usage at loss ({losses} losses / {wins} wins / {args.n} games) ===")
    print("\n-- Avg cards stranded in deck+prizes at loss (per game) --")
    for cid, tot in unseen_at_loss.most_common():
        deck_count = full[cid]
        print(f"  {nm(cid):16s} {tot/losses:.2f} / {deck_count} in deck")
    print("\n-- Avg dead cards in hand at loss (per game) --")
    for cid, tot in hand_at_loss.most_common(12):
        print(f"  {nm(cid):16s} {tot/losses:.2f}")
    if attack_turn_counts:
        print(f"\n-- Attacks per lost game: avg {sum(attack_turn_counts)/len(attack_turn_counts):.2f} --")


if __name__ == "__main__":
    main()
