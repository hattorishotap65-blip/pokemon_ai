"""
Action feature logging for ML shadow mode.

Extracts per-candidate-action features from game logs for future ML training.
No behavior change — reads existing logs only.

Usage:
  python experiments/action_feature_logging.py \
      --n 50 --start-game 130000 --run-games --use-wsl \
      --output artifacts/action_features_50g.jsonl
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from typing import Dict, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

_IONO_ENERGY_REQ = {"265": 2, "268": 1, "269": 4, "270": 1, "271": 3}
_MAIN_ATTACKERS = {"265", "269", "271"}
_ENGINE_CARDS = {"269"}


def _energy_needed(card_id: str, current_energy: int) -> int:
    req = _IONO_ENERGY_REQ.get(str(card_id))
    if req is None:
        return -1
    return max(0, req - (current_energy or 0))


def extract_candidate_features(
    cand: dict, entry: dict, state: dict, all_cands: list,
    game_result: str, game_id: int, decision_id: str = "",
) -> dict:
    """Extract features for one candidate action."""
    opt_type = cand.get("option_type")
    ss = state
    active_cid = str(ss.get("active_card_id", ""))
    active_hp = ss.get("active_hp", 0) or 0
    active_energy = ss.get("active_energy", 0) or 0
    opp_cid = str(ss.get("opp_active_card_id", ""))
    opp_hp = ss.get("opp_active_hp", 0) or 0
    prizes = ss.get("prizes_remaining", 6) or 6
    opp_prizes = ss.get("opp_prizes", 6) or 6
    bench_count = ss.get("bench_count", 0) or 0
    deck_count = ss.get("deck_count", 0) or 0
    hand_count = ss.get("hand_count", 0) or 0

    los = entry.get("legal_option_summary") or {}
    has_legal_attack = los.get("has_attack", False)
    legal_count = los.get("total", entry.get("legal_actions_count", 0))

    is_attack = bool(cand.get("is_attack")) or opt_type == 13
    is_end = bool(cand.get("is_end")) or opt_type == 14
    is_attach = opt_type == 8
    is_evolve = opt_type == 9
    is_ability = opt_type == 10
    is_play = opt_type in (3, 7)
    is_retreat = opt_type == 12

    active_e_needed = _energy_needed(active_cid, active_energy)
    reason = str(cand.get("reason", ""))

    attach_area = cand.get("inPlayArea")
    attach_to_active = is_attach and attach_area == 0
    attach_to_bench = is_attach and attach_area == 1
    attach_target_cid = str(cand.get("resolved_card_id") or cand.get("cardId") or "")

    attach_enables_attack = attach_to_active and active_e_needed == 1
    active_attach_would_enable = active_e_needed == 1

    can_ko = "ko" in reason.lower() and is_attack
    is_zero_damage = is_attack and ("zero_damage" in reason.lower() or "0_damage" in reason.lower())

    evolve_to_cid = str(cand.get("resolved_card_id") or "") if is_evolve else ""
    evolve_to_main = evolve_to_cid in _MAIN_ATTACKERS
    evolve_to_engine = evolve_to_cid in _ENGINE_CARDS

    late_game = prizes <= 2 or opp_prizes <= 2

    scores = sorted([c.get("final_score", 0) for c in all_cands], reverse=True)
    my_score = cand.get("final_score", 0)
    rank = scores.index(my_score) + 1 if my_score in scores else len(scores)

    return {
        "game_id": game_id,
        "decision_id": decision_id,
        "turn": ss.get("turn", 0),
        "action_index": cand.get("option_index", 0),
        "action_type": opt_type,
        "selected": bool(cand.get("selected")),
        "rule_score": round(my_score, 3),
        "rule_reason": reason,
        "candidate_rank": rank,
        "legal_action_count": legal_count,
        "has_legal_attack": has_legal_attack,
        "active_card_id": active_cid,
        "active_hp": active_hp,
        "active_energy": active_energy,
        "active_energy_needed": active_e_needed,
        "opponent_active_card_id": opp_cid,
        "opponent_active_hp": opp_hp,
        "bench_size": bench_count,
        "prize_remaining": prizes,
        "opponent_prize_remaining": opp_prizes,
        "prize_diff": prizes - opp_prizes,
        "deck_count": deck_count,
        "hand_count": hand_count,
        "is_attack": is_attack,
        "can_ko": can_ko,
        "is_zero_damage_attack": is_zero_damage,
        "attack_energy_ready": active_e_needed <= 0 if active_e_needed >= 0 else None,
        "is_attach": is_attach,
        "attach_to_active": attach_to_active,
        "attach_to_bench": attach_to_bench,
        "attach_target_card_id": attach_target_cid if is_attach else "",
        "attach_enables_attack": attach_enables_attack,
        "active_attach_would_enable": active_attach_would_enable,
        "is_evolve": is_evolve,
        "evolve_to_card_id": evolve_to_cid,
        "evolve_to_main_attacker": evolve_to_main,
        "evolve_to_engine": evolve_to_engine,
        "is_play": is_play,
        "is_ability": is_ability,
        "is_retreat": is_retreat,
        "is_end": is_end,
        "late_game": late_game,
        "game_result": game_result,
        "reward": _REWARD_MAP.get(game_result, 0.0),
    }


def _detect_game_result(entries: list) -> str:
    """Detect game result from log entries."""
    for e in reversed(entries):
        r = e.get("result")
        if r in ("win", "loss"):
            return r
        if e.get("error"):
            return "error"
    last = entries[-1] if entries else {}
    prizes = (last.get("state_summary") or {}).get("prizes_remaining", 6)
    opp_prizes = (last.get("state_summary") or {}).get("opp_prizes", 6)
    if prizes == 0:
        return "win"
    if opp_prizes == 0:
        return "loss"
    return "unknown"


_REWARD_MAP = {"win": 1.0, "loss": -1.0, "draw": 0.0, "error": -1.0, "timeout": -1.0}


def load_results_csv(csv_path: str, start_game: int) -> Dict[int, str]:
    """Load results CSV and return {game_id: winner} mapping."""
    import csv as csv_mod
    result_map: Dict[int, str] = {}
    if not csv_path or not os.path.exists(csv_path):
        return result_map
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                game_idx = int(row.get("game", 0))
                winner = (row.get("winner") or "").strip()
                gid = start_game + game_idx - 1
                result_map[gid] = winner
    except Exception:
        pass
    return result_map


def game_result_from_winner(winner: str) -> str:
    if winner == "p0":
        return "win"
    elif winner == "p1":
        return "loss"
    elif winner in ("timeout", "error"):
        return winner
    elif winner == "":
        return "draw"
    return "unknown"


def process_logs(start_game: int, count: int, output: str,
                 results_csv: str = "") -> dict:
    logs_dir = os.path.join(_REPO_ROOT, "logs")
    csv_results = load_results_csv(results_csv, start_game) if results_csv else {}
    stats = {
        "games": 0, "decisions": 0, "candidates": 0,
        "selected_by_type": {}, "errors": 0, "timeouts": 0,
        "can_ko_candidates": 0, "selected_can_ko": 0,
        "attach_enables_attack": 0, "selected_attach_enables": 0,
        "zero_damage_candidates": 0, "selected_zero_damage": 0,
        "matched_games": 0, "unmatched_games": 0,
        "reward_dist": {"win": 0, "loss": 0, "draw": 0, "error": 0, "timeout": 0, "unknown": 0},
    }

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as out_f:
        for gid in range(start_game, start_game + count):
            log_path = os.path.join(logs_dir, f"game_g{gid:05d}.jsonl")
            if not os.path.exists(log_path):
                continue

            stats["games"] += 1
            entries = []
            with open(log_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entries.append(json.loads(line.strip()))
                    except Exception:
                        continue

            if gid in csv_results:
                game_result = game_result_from_winner(csv_results[gid])
                stats["matched_games"] += 1
            else:
                game_result = _detect_game_result(entries)
                stats["unmatched_games"] += 1
            stats["reward_dist"][game_result] = stats["reward_dist"].get(game_result, 0) + 1
            if game_result == "error":
                stats["errors"] += 1
            elif game_result == "timeout":
                stats["timeouts"] += 1

            decision_seq = 0
            for entry in entries:
                candidates = entry.get("top_candidates") or []
                if not candidates:
                    continue

                decision_seq += 1
                did = f"{gid}-{decision_seq}"
                stats["decisions"] += 1
                ss = entry.get("state_summary") or {}

                for cand in candidates:
                    stats["candidates"] += 1
                    feat = extract_candidate_features(
                        cand, entry, ss, candidates, game_result, gid, did,
                    )
                    out_f.write(json.dumps(feat, ensure_ascii=False) + "\n")

                    sel = feat["selected"]
                    t = str(feat["action_type"])
                    if sel:
                        stats["selected_by_type"][t] = stats["selected_by_type"].get(t, 0) + 1
                    if feat["can_ko"]:
                        stats["can_ko_candidates"] += 1
                        if sel:
                            stats["selected_can_ko"] += 1
                    if feat["attach_enables_attack"]:
                        stats["attach_enables_attack"] += 1
                        if sel:
                            stats["selected_attach_enables"] += 1
                    if feat["is_zero_damage_attack"]:
                        stats["zero_damage_candidates"] += 1
                        if sel:
                            stats["selected_zero_damage"] += 1

    return stats


def run_games(n: int, start_game: int, use_wsl: bool) -> bool:
    if use_wsl:
        wsl_root = f"/mnt/c{_REPO_ROOT[2:].replace(os.sep, '/')}"
        cmd = (
            f'wsl -d Ubuntu -e bash -c "'
            f'cd {wsl_root} && '
            f'PYTHONPATH={wsl_root}/reference/extracted '
            f'python3 experiments/run_matches_real.py --n {n} --start-game {start_game}"'
        )
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            return False
    return False


def main():
    parser = argparse.ArgumentParser(description="Action feature logging for ML")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--start-game", type=int, default=130000)
    parser.add_argument("--output", default="artifacts/action_features.jsonl")
    parser.add_argument("--run-games", action="store_true")
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--results-csv", default="",
                        help="Results CSV from run_matches_real.py for reward labels")
    args = parser.parse_args()

    if args.run_games:
        print(f"Running {args.n} games starting at {args.start_game}...")
        ok = run_games(args.n, args.start_game, args.use_wsl)
        if not ok:
            print("WARNING: game execution failed or timed out")

    print(f"Processing logs {args.start_game}-{args.start_game + args.n - 1}...")
    stats = process_logs(args.start_game, args.n, args.output, args.results_csv)

    print(f"\nAction Feature Summary ({stats['games']} games):")
    print(f"  Decisions: {stats['decisions']}")
    print(f"  Candidates: {stats['candidates']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Selected by type: {stats['selected_by_type']}")
    print(f"  can_ko candidates: {stats['can_ko_candidates']}, selected: {stats['selected_can_ko']}")
    print(f"  attach_enables_attack: {stats['attach_enables_attack']}, selected: {stats['selected_attach_enables']}")
    print(f"  zero_damage candidates: {stats['zero_damage_candidates']}, selected: {stats['selected_zero_damage']}")
    print(f"  Matched games: {stats.get('matched_games', 0)}, Unmatched: {stats.get('unmatched_games', 0)}")
    print(f"  Reward dist: {stats.get('reward_dist', {})}")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
