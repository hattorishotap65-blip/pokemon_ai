"""
PRML ch.3-inspired data collection: log (feature_vector, final_outcome) pairs
for every one of my MAIN decisions, to later fit the linear board-evaluator
weights via ridge regression (fit_eval_weights.py) instead of hand-tuning.

Uses RagingBoltPolicy._extract_eval_features (the single source of truth
also used live by _eval_search_state) so fitted weights map onto the same
params.json keys.

Usage (inside WSL):
  python3 experiments/collect_eval_training_data.py --n 150 --opponent mirror \
      --output /tmp/eval_train_mirror.jsonl
  python3 experiments/collect_eval_training_data.py --n 150 --opponent lucario \
      --output /tmp/eval_train_lucario.jsonl
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "reference", "extracted"))


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_deck(path):
    with open(path, encoding="utf-8") as f:
        return [int(l.strip()) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--opponent", choices=["mirror", "lucario"], default="mirror")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    if sys.platform == "win32":
        print("ERROR: run inside WSL"); sys.exit(1)

    bolt_path = os.path.join(_REPO_ROOT, "experiments/agents/raging_bolt/main.py")
    bolt_mod = load_module(bolt_path, "bolt_collect")
    bolt_deck = bolt_mod.my_deck

    if args.opponent == "mirror":
        opp_agent, opp_deck = bolt_mod.agent, bolt_deck
    else:
        opp_mod = load_module(os.path.join(_REPO_ROOT, "experiments/agents/top_lucario_1084_main.py"),
                               "luc_collect")
        opp_agent = opp_mod.agent
        opp_deck = load_deck(os.path.join(_REPO_ROOT, "experiments/decks/top_lucario_1084.csv"))

    from cg.api import to_observation_class, SelectContext
    from cg.game import battle_finish, battle_select, battle_start

    out_f = open(args.output, "a", encoding="utf-8")
    total_rows = 0

    for gi in range(args.n):
        if gi % 2 == 0:
            d0, d1, ag0, ag1, bolt_idx = bolt_deck, opp_deck, bolt_mod.agent, opp_agent, 0
        else:
            d0, d1, ag0, ag1, bolt_idx = opp_deck, bolt_deck, opp_agent, bolt_mod.agent, 1

        obs = None
        game_rows = []
        result = None
        try:
            obs, sd = battle_start(d0, d1)
            if obs is None:
                continue
            for step in range(2000):
                obc = to_observation_class(obs)
                if obc.current.result >= 0:
                    result = "win" if obc.current.result == bolt_idx else (
                        "loss" if obc.current.result == (1 - bolt_idx) else "draw")
                    break
                is_bolt_turn = (obc.current.yourIndex == bolt_idx)
                if (is_bolt_turn and obc.select is not None
                        and obc.select.context == SelectContext.MAIN
                        and obc.select.option):
                    try:
                        policy = bolt_mod.RagingBoltPolicy(obc)
                        feats = policy._extract_eval_features(obc.current, bolt_idx)
                        game_rows.append(feats)
                    except Exception:
                        pass
                active_agent = ag0 if obc.current.yourIndex == 0 else ag1
                obs = battle_select(active_agent(obs))
        except Exception:
            result = None
        finally:
            if obs is not None:
                try:
                    battle_finish()
                except Exception:
                    pass

        if result in ("win", "loss") and game_rows:
            y = 1.0 if result == "win" else 0.0
            for feats in game_rows:
                out_f.write(json.dumps({"y": y, "x": feats}) + "\n")
            total_rows += len(game_rows)
            out_f.flush()

        if (gi + 1) % 20 == 0:
            print(f"  {gi+1}/{args.n} games, {total_rows} rows collected so far", flush=True)

    out_f.close()
    print(f"Done. {total_rows} total rows written to {args.output}")


if __name__ == "__main__":
    main()
