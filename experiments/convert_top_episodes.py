"""
Convert Kaggle Daily Top Episode JSON to intermediate JSONL
that analyze_top_episode_patterns.py can consume.

Usage:
  python experiments/convert_top_episodes.py \
      --inputs artifacts/top_episodes/81428291.json \
      --output artifacts/top_episodes_converted.jsonl

  python experiments/convert_top_episodes.py \
      --inputs artifacts/top_episodes/*.json \
      --output artifacts/top_episodes_converted.jsonl
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from typing import Dict, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)


def convert_episode(data: dict) -> List[dict]:
    """Convert one Kaggle episode JSON into a list of log entries
    compatible with analyze_top_episode_patterns.py."""
    episode_id = data.get("info", {}).get("EpisodeId", data.get("id", ""))
    teams = data.get("info", {}).get("TeamNames", ["p0", "p1"])
    rewards = data.get("rewards", [0, 0])
    steps = data.get("steps") or []

    entries = []
    for step_idx, step in enumerate(steps):
        for pi in range(min(2, len(step))):
            player = step[pi]
            obs = player.get("observation") or {}
            cur = obs.get("current") or {}
            sel = obs.get("select")
            action = player.get("action")

            if not sel or not sel.get("option"):
                continue

            options = sel["option"]
            if len(options) < 2:
                continue

            turn = cur.get("turn", 0)
            yi = cur.get("yourIndex", pi)

            action_indices = action if isinstance(action, list) else [action] if action is not None else [0]
            selected_idx = action_indices[0] if action_indices else 0

            players = cur.get("players") or []
            me = players[yi] if yi < len(players) and players[yi] else {}
            opp_idx = 1 - yi if len(players) > 1 else -1
            opp = players[opp_idx] if 0 <= opp_idx < len(players) and players[opp_idx] else {}

            active = me.get("active") or {}
            active_cid = str(active.get("cardId", "")) if isinstance(active, dict) else ""
            active_energy = len(active.get("energy", [])) if isinstance(active, dict) else 0

            opp_active = opp.get("active") or {}
            opp_active_cid = str(opp_active.get("cardId", "")) if isinstance(opp_active, dict) else ""

            bench = me.get("bench") or []
            prize_remain = me.get("prizeRemain", 6) if me else 6
            opp_prize = opp.get("prizeRemain", 6) if opp else 6

            candidates = []
            for oi, opt in enumerate(options):
                is_selected = (oi == selected_idx)
                opt_type = opt.get("type", 0)
                reason = ""
                can_ko = False

                candidates.append({
                    "option_index": oi,
                    "option_type": opt_type,
                    "selected": is_selected,
                    "is_attack": opt_type == 13,
                    "is_end": opt_type == 14,
                    "inPlayArea": opt.get("inPlayArea"),
                    "inPlayIndex": opt.get("inPlayIndex"),
                    "cardId": opt.get("cardId"),
                    "resolved_card_id": str(opt.get("cardId") or ""),
                    "reason": reason,
                    "rule_reason": reason,
                    "can_ko": can_ko,
                })

            entry = {
                "game_id": str(episode_id),
                "episode_id": str(episode_id),
                "step": step_idx,
                "game_turn": turn,
                "player": pi,
                "player_name": teams[pi] if pi < len(teams) else f"p{pi}",
                "state_summary": {
                    "turn": turn,
                    "active_card_id": active_cid,
                    "active_hp": 0,
                    "active_energy": active_energy,
                    "opp_active_card_id": opp_active_cid,
                    "opp_active_hp": 0,
                    "prizes_remaining": prize_remain,
                    "opp_prizes": opp_prize,
                    "bench_count": len(bench),
                    "deck_count": 0,
                    "hand_count": 0,
                },
                "top_candidates": candidates,
                "reward": rewards[pi] if pi < len(rewards) else 0,
            }
            entries.append(entry)

    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Convert Kaggle episode JSON to analysis JSONL"
    )
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="Episode JSON file paths (supports glob)")
    parser.add_argument("--output", default="artifacts/top_episodes_converted.jsonl")
    parser.add_argument("--max-episodes", type=int, default=0,
                        help="Max episodes to process (0=unlimited)")
    args = parser.parse_args()

    input_files = []
    for pattern in args.inputs:
        expanded = glob.glob(pattern)
        if expanded:
            input_files.extend(expanded)
        elif os.path.exists(pattern):
            input_files.append(pattern)

    if args.max_episodes > 0:
        input_files = input_files[:args.max_episodes]

    print(f"Converting {len(input_files)} episodes...")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    total_entries = 0
    total_episodes = 0

    with open(args.output, "w", encoding="utf-8") as out_f:
        for path in input_files:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                entries = convert_episode(data)
                for e in entries:
                    out_f.write(json.dumps(e, ensure_ascii=False) + "\n")
                total_entries += len(entries)
                total_episodes += 1
            except Exception as ex:
                print(f"  WARNING: {path}: {ex}")

    print(f"Converted {total_episodes} episodes, {total_entries} entries")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
