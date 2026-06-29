"""Build value model training dataset from simulation logs.

Usage:
    python experiments/web/value_dataset_builder.py --n 200
    python experiments/web/value_dataset_builder.py --traces experiments/web/human_traces/
"""
import csv
import json
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents", "raging_bolt"))


def build_from_simulation(n_games=100, output="experiments/web/value_dataset.csv"):
    """Run n games and collect (features, result) pairs."""
    import ctypes
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "reference", "extracted"))
    agent_dir = os.path.join(os.path.dirname(__file__), "..", "agents", "raging_bolt")
    sys.path.insert(0, agent_dir)
    os.chdir(agent_dir)

    from cg.game import battle_start, _get_battle_data
    from cg.api import to_observation_class, SelectContext
    from cg.sim import lib, Battle
    import main as rb
    from feature_extractor import extract_features, FEATURE_KEYS

    drag_dir = os.path.join(os.path.dirname(__file__), "..", "web", "agents", "dragapult")
    if not os.path.isdir(drag_dir):
        drag_dir = os.path.join(os.path.dirname(__file__), "agents", "dragapult")
    sys.path.insert(0, drag_dir)
    base_dir = os.path.join(os.path.dirname(__file__), "..", "web", "agents", "_base")
    if os.path.isdir(base_dir):
        sys.path.insert(0, base_dir)

    import types
    drag_mod = types.ModuleType("d")
    drag_mod.__dict__["__file__"] = os.path.join(drag_dir, "main.py")
    old = os.getcwd()
    os.chdir(drag_dir)
    exec(compile(open(os.path.join(drag_dir, "main.py")).read(),
                 os.path.join(drag_dir, "main.py"), "exec"), drag_mod.__dict__)
    os.chdir(old)
    drag_deck = [int(l) for l in open(os.path.join(drag_dir, "deck.csv")) if l.strip()]

    rows = []
    header = FEATURE_KEYS + ["turn", "result_win", "final_turn", "final_prize_diff"]

    for game_i in range(n_games):
        obs_dict, _ = battle_start(rb.my_deck, drag_deck)
        rb.pre_turn = -1
        rb.ability_used_teal_dance = False
        game_features = []

        for step in range(500):
            obs = to_observation_class(obs_dict)
            if obs.current.result != -1 or obs.select is None:
                winner = obs.current.result
                final_turn = obs.current.turn
                me = obs.current.players[0]
                opp = obs.current.players[1]
                result_win = 1 if winner == 0 else 0
                prize_diff = len(opp.prize) - len(me.prize)
                for feat_row in game_features:
                    feat_row["result_win"] = result_win
                    feat_row["final_turn"] = final_turn
                    feat_row["final_prize_diff"] = prize_diff
                    rows.append(feat_row)
                break

            pi = obs.current.yourIndex
            if pi == 0 and obs.select.context == SelectContext.MAIN:
                try:
                    features = extract_features(obs, 0)
                    features["turn"] = obs.current.turn
                    features["result_win"] = 0
                    features["final_turn"] = 0
                    features["final_prize_diff"] = 0
                    game_features.append(features)
                except Exception:
                    pass

            if pi == 0:
                action = rb.agent(obs_dict)
            else:
                try:
                    action = drag_mod.agent(obs_dict)
                except Exception:
                    nn = len(obs.select.option)
                    action = list(range(min(max(0, obs.select.minCount), nn)))

            arg = (ctypes.c_int * len(action))(*action)
            lib.Select(Battle.battle_ptr, arg, len(action))
            obs_dict = _get_battle_data()

        if game_i % 20 == 0:
            print("  %d/%d games, %d rows" % (game_i, n_games, len(rows)))

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print("Dataset: %d rows -> %s" % (len(rows), output))
    wins = sum(1 for r in rows if r["result_win"] == 1)
    print("Win rows: %d (%.1f%%)" % (wins, 100 * wins / len(rows) if rows else 0))
    return output


def build_from_traces(trace_dir, output="experiments/web/value_dataset_traces.csv"):
    """Build dataset from human trace JSONL files."""
    import glob
    try:
        from human_trace_writer import load_traces
    except ImportError:
        from experiments.web.human_trace_writer import load_traces
    from feature_extractor import FEATURE_KEYS

    header = FEATURE_KEYS + ["turn", "result_win", "final_turn", "final_prize_diff"]
    rows = []

    files = sorted(glob.glob(os.path.join(trace_dir, "*.jsonl")))
    for fp in files:
        entries = load_traces(fp)
        decisions = [e for e in entries if e.get("type", "decision") == "decision"]
        results = [e for e in entries if e.get("type") == "game_result"]
        result_win = 1 if results and results[0].get("result") == "win" else 0
        final_turn = results[0].get("turns", 0) if results else 0

        for e in decisions:
            if e.get("context") != "MAIN":
                continue
            my = e.get("my_active") or {}
            opp = e.get("opp_active") or {}
            row = {k: 0 for k in FEATURE_KEYS}
            row["my_prizes"] = e.get("my_prizes") or 6
            row["opp_prizes"] = e.get("opp_prizes") or 6
            row["prize_diff"] = row["my_prizes"] - row["opp_prizes"]
            row["my_active_hp"] = my.get("hp", 0)
            row["my_active_hp_pct"] = (my.get("hp", 0) * 100 // my.get("maxHp", 1)) if my.get("maxHp") else 0
            row["opp_active_hp"] = opp.get("hp", 0)
            row["hand_size"] = len(e.get("options", []))
            row["turn"] = e.get("turn", 0)
            row["result_win"] = result_win
            row["final_turn"] = final_turn
            row["final_prize_diff"] = 0
            rows.append(row)

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    print("Trace dataset: %d rows -> %s" % (len(rows), output))
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--traces", default="")
    parser.add_argument("--output", default="experiments/web/value_dataset.csv")
    args = parser.parse_args()

    if args.traces:
        build_from_traces(args.traces, args.output)
    else:
        build_from_simulation(args.n, args.output)


if __name__ == "__main__":
    main()
