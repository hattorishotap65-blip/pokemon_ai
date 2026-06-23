"""
Loss pattern diagnostics — classify bad decision patterns from game logs.

No behavior change. Reads existing logs and classifies decisions.

Usage:
  python experiments/loss_pattern_diagnostics.py \
      --n 50 --start-game 120000 --run-games --use-wsl \
      --output artifacts/loss_pattern_50g.json
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

_MAX_EXAMPLES = 30

_IONO_ENERGY_REQ = {"265": 2, "268": 1, "269": 4, "270": 1, "271": 3}


def init_patterns() -> dict:
    return {
        "decisions": 0,
        "games": 0,
        "selected_end_with_legal_attack": 0,
        "missed_ko_attack": 0,
        "zero_damage_attack_selected": 0,
        "active_attach_miss": 0,
        "bench_over_setup": 0,
        "timeout_or_error": 0,
        "game_losses": 0,
        "game_wins": 0,
    }


def _get_legal_summary(entry: dict) -> dict:
    los = entry.get("legal_option_summary") or {}
    return {
        "has_attack": los.get("has_attack", False),
        "attack_count": los.get("attack", 0),
        "total": los.get("total", 0),
    }


def _selected_cand(candidates: list) -> dict:
    for c in candidates:
        if c.get("selected"):
            return c
    return candidates[0] if candidates else {}


def _is_attack(cand: dict) -> bool:
    return bool(cand.get("is_attack")) or cand.get("option_type") == 13


def _is_end(cand: dict) -> bool:
    return bool(cand.get("is_end")) or cand.get("option_type") == 14


def _is_attach(cand: dict) -> bool:
    return cand.get("option_type") == 8


def _active_energy_needed(state_summary: dict) -> int:
    cid = str(state_summary.get("active_card_id", ""))
    req = _IONO_ENERGY_REQ.get(cid)
    if req is None:
        return 999
    current = state_summary.get("active_energy", 0) or 0
    return max(0, req - current)


def _has_ko_candidate(candidates: list, state_summary: dict) -> bool:
    opp_hp = state_summary.get("opp_active_hp", 9999) or 9999
    for c in candidates:
        if not _is_attack(c):
            continue
        reason = str(c.get("reason", ""))
        if "ko" in reason.lower():
            return True
    return False


def _attach_target_is_bench(cand: dict) -> bool:
    if not _is_attach(cand):
        return False
    area = cand.get("inPlayArea")
    if area is not None:
        return area == 1
    return False


def _attach_target_is_active(cand: dict) -> bool:
    if not _is_attach(cand):
        return False
    area = cand.get("inPlayArea")
    if area is not None:
        return area == 0
    return False


def classify_decision(entry: dict, candidates: list, sel: dict,
                      state_summary: dict) -> List[str]:
    """Return list of pattern tags for this decision."""
    tags = []
    legal = _get_legal_summary(entry)
    energy_needed = _active_energy_needed(state_summary)

    if _is_end(sel) and legal["has_attack"]:
        tags.append("selected_end_with_legal_attack")

    if _has_ko_candidate(candidates, state_summary) and not _is_attack(sel):
        tags.append("missed_ko_attack")

    if _is_attack(sel):
        reason = str(sel.get("reason", ""))
        if "zero_damage" in reason.lower() or "0_damage" in reason.lower():
            tags.append("zero_damage_attack_selected")

    if _is_attach(sel) and _attach_target_is_bench(sel) and energy_needed <= 1:
        tags.append("active_attach_miss")

    if _is_attach(sel) and _attach_target_is_bench(sel) and not legal["has_attack"]:
        atk_cands = [c for c in candidates if _is_attack(c)]
        if not atk_cands and energy_needed > 2:
            tags.append("bench_over_setup")

    return tags


def analyze_logs(start_game: int, count: int) -> dict:
    logs_dir = os.path.join(_REPO_ROOT, "logs")
    patterns = init_patterns()
    examples: List[dict] = []
    game_results = {"p0": 0, "p1": 0, "timeout": 0, "error": 0, "other": 0}

    for gid in range(start_game, start_game + count):
        log_path = os.path.join(logs_dir, f"game_g{gid:05d}.jsonl")
        if not os.path.exists(log_path):
            continue

        patterns["games"] += 1
        entries = []
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except Exception:
                    continue

        last = entries[-1] if entries else {}
        result = last.get("result")
        if result == "win":
            patterns["game_wins"] += 1
            game_results["p0"] += 1
        elif result == "loss":
            patterns["game_losses"] += 1
            game_results["p1"] += 1
        elif last.get("error"):
            patterns["timeout_or_error"] += 1
            game_results["error"] += 1

        for entry in entries:
            candidates = entry.get("top_candidates") or []
            if not candidates:
                continue

            patterns["decisions"] += 1
            state_summary = entry.get("state_summary") or {}
            sel = _selected_cand(candidates)
            tags = classify_decision(entry, candidates, sel, state_summary)

            for tag in tags:
                if tag in patterns:
                    patterns[tag] += 1

            if tags and len(examples) < _MAX_EXAMPLES:
                examples.append({
                    "game_id": gid,
                    "turn": state_summary.get("turn", 0),
                    "active": state_summary.get("active_card_id", ""),
                    "active_hp": state_summary.get("active_hp", 0),
                    "active_energy": state_summary.get("active_energy", 0),
                    "opp_active": state_summary.get("opp_active_card_id", ""),
                    "opp_hp": state_summary.get("opp_active_hp", 0),
                    "selected_type": sel.get("option_type"),
                    "selected_reason": sel.get("reason", ""),
                    "tags": tags,
                })

    d = patterns["decisions"] or 1
    rates = {k: round(patterns[k] / d, 4)
             for k in patterns if k not in ("decisions", "games", "game_wins", "game_losses")}

    return {
        "games": count,
        "start_game": start_game,
        "patterns": patterns,
        "rates": rates,
        "game_results": game_results,
        "examples": examples,
    }


def save_result(path: str, result: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


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
    parser = argparse.ArgumentParser(description="Loss pattern diagnostics")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--start-game", type=int, default=120000)
    parser.add_argument("--output", default="artifacts/loss_pattern_diagnostics.json")
    parser.add_argument("--run-games", action="store_true")
    parser.add_argument("--use-wsl", action="store_true")
    args = parser.parse_args()

    if args.run_games:
        print(f"Running {args.n} games starting at {args.start_game}...")
        ok = run_games(args.n, args.start_game, args.use_wsl)
        if not ok:
            print("WARNING: game execution failed or timed out")

    print(f"Analyzing logs {args.start_game}-{args.start_game + args.n - 1}...")
    result = analyze_logs(args.start_game, args.n)
    save_result(args.output, result)

    p = result["patterns"]
    print(f"\nLoss Pattern Summary ({p['games']} games, {p['decisions']} decisions):")
    print(f"  Wins: {p['game_wins']}, Losses: {p['game_losses']}")
    for k in ["selected_end_with_legal_attack", "missed_ko_attack",
              "zero_damage_attack_selected", "active_attach_miss",
              "bench_over_setup", "timeout_or_error"]:
        print(f"  {k}: {p[k]}")
    print(f"  Examples: {len(result['examples'])}")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
