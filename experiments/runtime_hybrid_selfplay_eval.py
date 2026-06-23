"""
Runtime-style ML hybrid self-play evaluation.

Trains DecisionTreeRanker on 50g, then re-evaluates 100g logs
using safety-gated hybrid scoring. Measures win-rate, safety,
and decision change impact by comparing rule vs hybrid selections.

This does NOT modify policy.py. It simulates hybrid by offline
re-ranking logged decisions.

Usage:
  python experiments/runtime_hybrid_selfplay_eval.py \
      --train artifacts/train.jsonl --eval artifacts/eval.jsonl \
      --bonus-ratios 0,5,10,20 \
      --summary artifacts/runtime_hybrid_summary.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Dict, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

from experiments.ml_shadow_scoring import (
    DecisionTreeRanker, load_jsonl, group_by_decision, _NO_RULE_FEATURES,
)
from experiments.ml_hybrid_safety_eval import apply_safety_gate


def evaluate_hybrid_winrate(
    model: DecisionTreeRanker,
    eval_data: List[dict],
    bonus_ratio: float,
) -> dict:
    """Evaluate hybrid re-ranking: measure how often hybrid changes the
    selected action and whether changed games have different outcomes."""
    groups = group_by_decision(eval_data)
    game_decisions: Dict[int, List[dict]] = {}

    stats = {
        "decisions": len(groups), "candidates": len(eval_data),
        "changed": 0, "unchanged": 0,
        "end_legal_attack": 0, "zero_damage": 0, "miss_ko": 0,
        "gate_blocked": 0,
        "rule_type_dist": {}, "hybrid_type_dist": {},
    }

    for key, cands in groups.items():
        has_legal_attack = any(c.get("has_legal_attack") for c in cands)
        has_ko = any(c.get("can_ko") for c in cands)

        ml_scores = [model.score(c) for c in cands]
        ml_min = min(ml_scores) if ml_scores else 0
        ml_max = max(ml_scores) if ml_scores else 1
        ml_range = ml_max - ml_min if ml_max > ml_min else 1.0

        hybrid_scored = []
        for i, c in enumerate(cands):
            gate = apply_safety_gate(c, has_legal_attack, has_ko)
            norm = (ml_scores[i] - ml_min) / ml_range
            bonus = bonus_ratio * norm if gate["allowed"] else 0.0
            if not gate["allowed"]:
                stats["gate_blocked"] += 1
            hybrid_scored.append((c.get("rule_score", 0) + bonus, c))

        rule_sorted = sorted(cands, key=lambda c: c.get("rule_score", 0), reverse=True)
        hybrid_sorted = sorted(hybrid_scored, key=lambda x: x[0], reverse=True)

        rule_top = rule_sorted[0] if rule_sorted else {}
        hybrid_top = hybrid_sorted[0][1] if hybrid_sorted else {}

        if rule_top.get("action_index") != hybrid_top.get("action_index"):
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1

        rt = str(rule_top.get("action_type", ""))
        ht = str(hybrid_top.get("action_type", ""))
        stats["rule_type_dist"][rt] = stats["rule_type_dist"].get(rt, 0) + 1
        stats["hybrid_type_dist"][ht] = stats["hybrid_type_dist"].get(ht, 0) + 1

        if hybrid_top.get("is_end") and has_legal_attack:
            stats["end_legal_attack"] += 1
        if hybrid_top.get("is_zero_damage_attack"):
            stats["zero_damage"] += 1
        if has_ko and not hybrid_top.get("is_attack"):
            stats["miss_ko"] += 1

        gid = cands[0].get("game_id", 0) if cands else 0
        if gid not in game_decisions:
            game_decisions[gid] = []
        game_decisions[gid].append({
            "changed": rule_top.get("action_index") != hybrid_top.get("action_index"),
            "rule_type": rt, "hybrid_type": ht,
        })

    # Per-game analysis
    game_stats = {"total": 0, "changed_games": 0}
    game_results = {}
    for row in eval_data:
        gid = row.get("game_id", 0)
        game_results[gid] = row.get("game_result", "unknown")

    wins = losses = unknown = 0
    changed_wins = changed_losses = 0
    for gid, decisions in game_decisions.items():
        game_stats["total"] += 1
        any_changed = any(d["changed"] for d in decisions)
        if any_changed:
            game_stats["changed_games"] += 1
        result = game_results.get(gid, "unknown")
        if result == "win":
            wins += 1
            if any_changed:
                changed_wins += 1
        elif result == "loss":
            losses += 1
            if any_changed:
                changed_losses += 1
        else:
            unknown += 1

    d = stats["decisions"] or 1
    stats["changed_rate"] = round(stats["changed"] / d, 4)
    stats["games"] = game_stats["total"]
    stats["changed_games"] = game_stats["changed_games"]
    stats["wins"] = wins
    stats["losses"] = losses
    stats["win_rate"] = round(wins / (wins + losses), 4) if (wins + losses) else 0.0
    stats["changed_game_wins"] = changed_wins
    stats["changed_game_losses"] = changed_losses
    return stats


def main():
    parser = argparse.ArgumentParser(description="Runtime hybrid self-play eval")
    parser.add_argument("--train", required=True)
    parser.add_argument("--eval", required=True)
    parser.add_argument("--summary", default="artifacts/runtime_hybrid_summary.json")
    parser.add_argument("--bonus-ratios", default="0,5,10,20")
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--min-leaf", type=int, default=20)
    args = parser.parse_args()

    ratios = [float(r) for r in args.bonus_ratios.split(",")]

    print(f"Loading train data from {args.train}...")
    train_data = load_jsonl(args.train)
    print(f"  {len(train_data)} rows")

    print(f"\nTraining DecisionTreeRanker...")
    model = DecisionTreeRanker(
        feature_list=_NO_RULE_FEATURES,
        max_depth=args.max_depth, min_samples_leaf=args.min_leaf,
    )
    model.train(train_data)

    print(f"\nLoading eval data from {args.eval}...")
    eval_data = load_jsonl(args.eval)
    print(f"  {len(eval_data)} rows")

    all_results = {}
    for ratio in ratios:
        print(f"\n--- Bonus ratio: {ratio} ---")
        stats = evaluate_hybrid_winrate(model, eval_data, ratio)
        all_results[str(ratio)] = stats
        print(f"  Decisions: {stats['decisions']}")
        print(f"  Changed: {stats['changed']} ({stats['changed_rate']:.1%})")
        print(f"  Games: {stats['games']}, Changed games: {stats['changed_games']}")
        print(f"  Wins: {stats['wins']}, Losses: {stats['losses']}, Win rate: {stats['win_rate']:.1%}")
        print(f"  End+legal_attack: {stats['end_legal_attack']}")
        print(f"  Zero damage: {stats['zero_damage']}")
        print(f"  Miss KO: {stats['miss_ko']}")
        print(f"  Gate blocked: {stats['gate_blocked']}")

    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {args.summary}")


if __name__ == "__main__":
    main()
