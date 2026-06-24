"""
Cache Top Episode features for fast comparison.

Converts raw Kaggle episode JSON → per-decision feature JSONL
that compare_candidate_vs_top_cached.py can load instantly.

Usage:
  python experiments/cache_top_episode_features.py \
      --input artifacts/top_episodes/*.json \
      --output artifacts/top_episodes_features_cached.jsonl
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
import time
from typing import Dict, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

_AREA_ACTIVE = 4
_AREA_BENCH = 5
_MAIN_ATTACKERS = {"265", "269", "271"}
_IONO_ENERGY_REQ = {"265": 2, "268": 1, "269": 4, "270": 1, "271": 3}

_ACTION_NAMES = {
    0: "NUMBER", 1: "YES", 2: "NO", 3: "CARD", 4: "TOOL_CARD",
    5: "ENERGY_CARD", 6: "ENERGY", 7: "PLAY", 8: "ATTACH",
    9: "EVOLVE", 10: "ABILITY", 11: "DISCARD", 12: "RETREAT",
    13: "ATTACK", 14: "END", 15: "SKILL", 16: "SPECIAL_CONDITION",
}


def _phase(turn: int) -> str:
    if turn <= 3:
        return "early"
    if turn <= 8:
        return "mid"
    return "late"


def extract_features_from_episode(data: dict) -> List[dict]:
    episode_id = data.get("info", {}).get("EpisodeId", data.get("id", ""))
    steps = data.get("steps") or []
    features = []

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
            opp_idx = 1 - yi
            opp = players[opp_idx] if 0 <= opp_idx < len(players) and players[opp_idx] else {}

            active = me.get("active") or {}
            active_cid = str(active.get("cardId", "")) if isinstance(active, dict) else ""
            active_energy = len(active.get("energy", [])) if isinstance(active, dict) else 0

            opt_types = [o.get("type", 0) for o in options]
            has_legal_attack = 13 in opt_types
            has_end = 14 in opt_types
            selected_type = options[selected_idx].get("type", 0) if selected_idx < len(options) else 0
            selected_opt = options[selected_idx] if selected_idx < len(options) else {}

            is_attack = selected_type == 13
            is_end = selected_type == 14
            is_attach = selected_type == 8
            is_retreat = selected_type == 12

            attach_area = selected_opt.get("inPlayArea") if is_attach else None
            attach_to_active = is_attach and attach_area == _AREA_ACTIVE
            attach_to_bench = is_attach and attach_area == _AREA_BENCH

            req = _IONO_ENERGY_REQ.get(active_cid, 0)
            active_energy_needed = max(0, req - active_energy) if req > 0 else 0
            is_main_attacker = active_cid in _MAIN_ATTACKERS
            active_energy_starved = (
                attach_to_bench and active_energy_needed > 0 and is_main_attacker
            )
            bench_oversetup = False

            features.append({
                "episode_id": str(episode_id),
                "player": pi,
                "turn": turn,
                "phase": _phase(turn),
                "step": step_idx,
                "action_type": selected_type,
                "action_name": _ACTION_NAMES.get(selected_type, str(selected_type)),
                "has_legal_attack": has_legal_attack,
                "is_attack": is_attack,
                "is_end": is_end,
                "is_attach": is_attach,
                "is_retreat": is_retreat,
                "attach_to_active": attach_to_active,
                "attach_to_bench": attach_to_bench,
                "active_energy_starved": active_energy_starved,
                "bench_oversetup": bench_oversetup,
                "attack_when_legal": is_attack and has_legal_attack,
                "end_when_legal_attack": is_end and has_legal_attack,
                "zero_damage": False,
                "active_card": active_cid,
                "active_energy_count": active_energy,
                "active_energy_needed": active_energy_needed,
                "is_main_attacker": is_main_attacker,
                "n_options": len(options),
            })

    return features


def main():
    parser = argparse.ArgumentParser(
        description="Cache Top Episode features for fast comparison"
    )
    parser.add_argument("--input", nargs="+", required=True,
                        help="Raw episode JSON files (supports glob)")
    parser.add_argument("--output", default="artifacts/top_episodes_features_cached.jsonl")
    args = parser.parse_args()

    input_files = []
    for pattern in args.input:
        expanded = glob.glob(pattern)
        if expanded:
            input_files.extend(expanded)
        elif os.path.exists(pattern):
            input_files.append(pattern)

    print(f"Caching features from {len(input_files)} episodes...")
    t0 = time.time()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    total = 0
    with open(args.output, "w", encoding="utf-8") as out_f:
        for path in input_files:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                feats = extract_features_from_episode(data)
                for feat in feats:
                    out_f.write(json.dumps(feat, ensure_ascii=False) + "\n")
                total += len(feats)
            except Exception as ex:
                print(f"  WARNING: {path}: {ex}")

    elapsed = time.time() - t0
    print(f"Cached {total} decisions from {len(input_files)} episodes in {elapsed:.1f}s")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
