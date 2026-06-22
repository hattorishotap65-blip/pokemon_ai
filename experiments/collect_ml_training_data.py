"""
Collect ML training data from rule-based agent games.

Hooks into the agent's action selection to record every candidate
action with features, score, and whether it was selected.

Usage:
  python experiments/collect_ml_training_data.py --n 5 --start-game 80000 \
      --output artifacts/ml_training_data.jsonl --max-examples 500

  python experiments/collect_ml_training_data.py --n 30 --start-game 81000 \
      --output artifacts/ml_training_data.jsonl --max-examples 5000 --use-wsl
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)


def _run_games(n: int, start_game: int, use_wsl: bool) -> bool:
    if use_wsl:
        wsl_root = f"/mnt/c{_REPO_ROOT[2:].replace(os.sep, '/')}"
        cmd = (
            f'wsl -d Ubuntu -e bash -c '
            f'"cd {wsl_root} && '
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


def _extract_from_logs(start_game: int, count: int, output: str,
                       max_examples: int, include_unselected: bool) -> int:
    """Parse game logs and extract training examples."""
    from agent.ml_features import extract_features
    from agent.ml_training_logger import make_training_example, append_jsonl

    logs_dir = os.path.join(_REPO_ROOT, "logs")
    total = 0

    for gid in range(start_game, start_game + count):
        log_path = os.path.join(logs_dir, f"game_g{gid:05d}.jsonl")
        if not os.path.exists(log_path):
            continue

        with open(log_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                if total >= max_examples:
                    return total
                try:
                    entry = json.loads(line.strip())
                except Exception:
                    continue

                if entry.get("event") != "decision":
                    continue

                state = entry.get("state") or {}
                candidates = entry.get("candidates") or []
                selected_idx = entry.get("selected_index", 0)

                decision_id = f"{gid}-{line_no}"

                for ci, cand in enumerate(candidates):
                    if total >= max_examples:
                        return total

                    action = cand.get("action") or {}
                    score = cand.get("score", 0.0)
                    reason = cand.get("reason", "")
                    breakdown = cand.get("breakdown")
                    is_selected = (ci == selected_idx)

                    if not include_unselected and not is_selected:
                        continue

                    features = extract_features(state, action)

                    ex = make_training_example(
                        state=state, action=action, selected=is_selected,
                        score=score, reason=reason, breakdown=breakdown,
                        features=features, game_id=gid,
                        decision_id=decision_id, candidate_index=ci,
                    )
                    append_jsonl(output, ex)
                    total += 1

    return total


def _extract_from_real_logs(start_game: int, count: int, output: str,
                           max_examples: int, include_unselected: bool) -> int:
    """Extract training data from real game logs (top_candidates format)."""
    from agent.ml_features import extract_features
    from agent.ml_training_logger import make_training_example, append_jsonl

    logs_dir = os.path.join(_REPO_ROOT, "logs")
    total = 0

    for gid in range(start_game, start_game + count):
        log_path = os.path.join(logs_dir, f"game_g{gid:05d}.jsonl")
        if not os.path.exists(log_path):
            continue

        with open(log_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                if total >= max_examples:
                    return total
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

                decision_id = f"{gid}-{line_no}"

                for ci, cand in enumerate(candidates):
                    if total >= max_examples:
                        return total

                    is_selected = cand.get("selected", False)
                    if not include_unselected and not is_selected:
                        continue

                    action = {
                        "type": cand.get("option_type"),
                        "cardId": cand.get("resolved_card_id"),
                    }

                    breakdown = {
                        "type_score": cand.get("type_score", 0),
                        "rule_bonus": cand.get("rule_bonus", 0),
                        "turn_rule_score": cand.get("turn_rule_score", 0),
                        "final_score": cand.get("final_score", 0),
                        "is_attack": cand.get("is_attack", False),
                        "is_ability": cand.get("is_ability", False),
                        "is_retreat": cand.get("is_retreat", False),
                        "is_end": cand.get("is_end", False),
                    }

                    features = extract_features(state, action)
                    features["final_score"] = cand.get("final_score", 0)
                    features["option_class"] = cand.get("option_class", "")

                    score = cand.get("final_score", 0.0)
                    reason = cand.get("reason", "")

                    ex = make_training_example(
                        state=state, action=action, selected=is_selected,
                        score=score, reason=reason, breakdown=breakdown,
                        features=features, game_id=gid,
                        decision_id=decision_id, candidate_index=ci,
                    )
                    append_jsonl(output, ex)
                    total += 1

    return total


def main():
    parser = argparse.ArgumentParser(description="Collect ML training data")
    parser.add_argument("--n", type=int, default=5, help="Games to play")
    parser.add_argument("--start-game", type=int, default=80000)
    parser.add_argument("--output", default="artifacts/ml_training_data.jsonl")
    parser.add_argument("--max-examples", type=int, default=5000)
    parser.add_argument("--include-unselected", action="store_true")
    parser.add_argument("--use-wsl", action="store_true")
    parser.add_argument("--skip-games", action="store_true",
                        help="Skip game execution, only extract from existing logs")
    args = parser.parse_args()

    if not args.skip_games:
        print(f"Running {args.n} games starting at {args.start_game}...")
        ok = _run_games(args.n, args.start_game, args.use_wsl)
        if not ok:
            print("WARNING: game execution failed or timed out")

    # Remove existing output to avoid appending to old data
    if os.path.exists(args.output):
        os.remove(args.output)

    print(f"Extracting training data...")
    total = _extract_from_real_logs(
        args.start_game, args.n, args.output, args.max_examples,
        args.include_unselected,
    )

    print(f"Done: {total} examples written to {args.output}")

    if os.path.exists(args.output):
        with open(args.output) as f:
            lines = f.readlines()
        valid = sum(1 for l in lines if l.strip())
        selected = sum(1 for l in lines if '"selected": true' in l)
        print(f"  Lines: {valid}, Selected: {selected}")


if __name__ == "__main__":
    main()
