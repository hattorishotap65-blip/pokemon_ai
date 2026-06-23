"""
Collect attack_plan diagnostics from game logs.

Analyzes existing game logs to detect missed KO plans,
missed high-value plans, and end-with-plan-available cases.

Usage:
  # First run games to generate logs:
  python experiments/run_matches_real.py --n 50 --start-game 97000

  # Then collect diagnostics from those logs:
  python experiments/collect_attack_plan_diagnostics.py \
      --n 50 --start-game 97000 \
      --output artifacts/attack_plan_diagnostics_50g.json

  # Or run games + collect in one step (WSL):
  python experiments/collect_attack_plan_diagnostics.py \
      --n 50 --start-game 97000 \
      --output artifacts/attack_plan_diagnostics_50g.json \
      --run-games --use-wsl
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

_MAX_EXAMPLES = 20


def init_summary() -> dict:
    return {
        "decisions": 0,
        "plans_available": 0,
        "chosen_matches_best": 0,
        "chosen_matches_any": 0,
        "missed_high_value_plan": 0,
        "missed_ko_plan": 0,
        "end_with_plan_available": 0,
        "has_winning_ko": 0,
        "has_active_ko": 0,
        "has_boss_ko": 0,
        "has_zero_damage_escape": 0,
        "diagnostic_errors": 0,
    }


def add_diagnosis(summary: dict, diag: dict, plan_summary: dict):
    summary["decisions"] += 1
    if plan_summary.get("plan_count", 0) > 0:
        summary["plans_available"] += 1
    if diag.get("chosen_matches_best"):
        summary["chosen_matches_best"] += 1
    if diag.get("chosen_matches_any"):
        summary["chosen_matches_any"] += 1
    if diag.get("missed_high_value_plan"):
        summary["missed_high_value_plan"] += 1
    if diag.get("missed_ko_plan"):
        summary["missed_ko_plan"] += 1
    for note in diag.get("notes", []):
        if note == "end_with_plan_available":
            summary["end_with_plan_available"] += 1
    if plan_summary.get("has_winning_ko"):
        summary["has_winning_ko"] += 1
    if plan_summary.get("has_active_ko"):
        summary["has_active_ko"] += 1
    if plan_summary.get("has_boss_ko"):
        summary["has_boss_ko"] += 1
    if plan_summary.get("has_zero_damage_escape"):
        summary["has_zero_damage_escape"] += 1


def compute_rates(summary: dict) -> dict:
    d = summary.get("decisions", 0)
    pa = summary.get("plans_available", 0)
    return {
        "missed_ko_plan_rate": round(summary["missed_ko_plan"] / pa, 4) if pa else 0.0,
        "missed_high_value_plan_rate": round(summary["missed_high_value_plan"] / pa, 4) if pa else 0.0,
        "chosen_matches_best_rate": round(summary["chosen_matches_best"] / pa, 4) if pa else 0.0,
        "end_with_plan_rate": round(summary["end_with_plan_available"] / pa, 4) if pa else 0.0,
    }


def analyze_logs(start_game: int, count: int) -> dict:
    """Analyze game logs and collect attack_plan diagnostics."""
    from agent.attack_plan import (
        generate_attack_plans, summarize_attack_plans,
        diagnose_attack_plan_choice, clear_attack_plan_cache,
    )

    logs_dir = os.path.join(_REPO_ROOT, "logs")
    summary = init_summary()
    examples: List[dict] = []

    for gid in range(start_game, start_game + count):
        log_path = os.path.join(logs_dir, f"game_g{gid:05d}.jsonl")
        if not os.path.exists(log_path):
            continue

        with open(log_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                try:
                    entry = json.loads(line.strip())
                except Exception:
                    continue

                candidates = entry.get("top_candidates") or []
                if not candidates:
                    continue

                state_summary = entry.get("state_summary") or {}
                state = {
                    "turn": state_summary.get("turn", 0),
                    "prizes_remaining": state_summary.get("prizes_remaining", 0),
                    "deck_count": state_summary.get("deck_count", 0),
                    "hand_count": state_summary.get("hand_count", 0),
                    "active_pokemon": {
                        "card_id": state_summary.get("active_card_id", ""),
                        "hp_remaining": state_summary.get("active_hp", 0),
                        "energy_count": state_summary.get("active_energy", 0),
                    },
                    "bench": [{}] * state_summary.get("bench_count", 0),
                    "opponent": {
                        "prizes_remaining": state_summary.get("opp_prizes", 0),
                        "active_pokemon": {
                            "card_id": state_summary.get("opp_active_card_id", ""),
                            "hp_remaining": state_summary.get("opp_active_hp", 0),
                        },
                        "bench": [],
                    },
                }

                selected_cand = None
                for c in candidates:
                    if c.get("selected"):
                        selected_cand = c
                        break
                if not selected_cand:
                    selected_cand = candidates[0]

                chosen_action = {
                    "type": selected_cand.get("option_type"),
                    "cardId": selected_cand.get("resolved_card_id"),
                }

                try:
                    clear_attack_plan_cache()
                    plans = generate_attack_plans(state)
                    ps = summarize_attack_plans(plans)
                    diag = diagnose_attack_plan_choice(plans, chosen_action, state)
                    add_diagnosis(summary, diag, ps)

                    if diag.get("notes") and len(examples) < _MAX_EXAMPLES:
                        examples.append({
                            "game_id": gid,
                            "turn": state_summary.get("turn", 0),
                            "best_plan_type": diag["best_plan_type"],
                            "best_plan_score": diag["best_plan_score"],
                            "chosen_action_type": chosen_action.get("type"),
                            "notes": diag["notes"],
                        })
                except Exception:
                    summary["diagnostic_errors"] += 1

    return {
        "games": count,
        "start_game": start_game,
        "summary": summary,
        "rates": compute_rates(summary),
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
    else:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(_REPO_ROOT, "reference", "extracted")
        try:
            r = subprocess.run(
                [sys.executable, "experiments/run_matches_real.py",
                 "--n", str(n), "--start-game", str(start_game)],
                cwd=_REPO_ROOT, capture_output=True, text=True, timeout=600, env=env,
            )
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            return False


def main():
    parser = argparse.ArgumentParser(description="Collect attack plan diagnostics")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--start-game", type=int, default=97000)
    parser.add_argument("--output", default="artifacts/attack_plan_diagnostics.json")
    parser.add_argument("--run-games", action="store_true")
    parser.add_argument("--use-wsl", action="store_true")
    args = parser.parse_args()

    if args.run_games:
        print(f"Running {args.n} games starting at {args.start_game}...")
        ok = run_games(args.n, args.start_game, args.use_wsl)
        if not ok:
            print("WARNING: game execution failed or timed out")

    print(f"Analyzing logs for games {args.start_game}-{args.start_game + args.n - 1}...")
    result = analyze_logs(args.start_game, args.n)

    save_result(args.output, result)
    s = result["summary"]
    r = result["rates"]
    print(f"\nDiagnostics Summary:")
    print(f"  Decisions: {s['decisions']}")
    print(f"  Plans available: {s['plans_available']}")
    print(f"  Chosen matches best: {s['chosen_matches_best']} ({r['chosen_matches_best_rate']:.1%})")
    print(f"  Missed KO plan: {s['missed_ko_plan']} ({r['missed_ko_plan_rate']:.1%})")
    print(f"  Missed high-value: {s['missed_high_value_plan']} ({r['missed_high_value_plan_rate']:.1%})")
    print(f"  End with plan: {s['end_with_plan_available']} ({r['end_with_plan_rate']:.1%})")
    print(f"  Diagnostic errors: {s['diagnostic_errors']}")
    print(f"  Examples: {len(result['examples'])}")
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
