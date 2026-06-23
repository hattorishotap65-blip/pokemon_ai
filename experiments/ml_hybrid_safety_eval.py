"""
Safety-gated ML hybrid scoring evaluation.

Trains DecisionTreeRanker, applies safety gates, and evaluates
hybrid scoring (rule_score + small ML bonus) offline.

Usage:
  python experiments/ml_hybrid_safety_eval.py \
      --train artifacts/train.jsonl --eval artifacts/eval.jsonl \
      --output artifacts/hybrid_eval.jsonl --summary artifacts/hybrid_summary.json
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
    DecisionTreeRanker, load_jsonl, group_by_decision,
    _NO_RULE_FEATURES,
)

_ML_BONUS_SCALE = 1.0


def apply_safety_gate(cand: dict, has_legal_attack: bool, has_ko_cand: bool) -> dict:
    """Check safety gates. Returns {allowed, reason}."""
    if cand.get("is_end") and has_legal_attack:
        return {"allowed": False, "reason": "gate_end_legal_attack"}
    if cand.get("is_zero_damage_attack"):
        return {"allowed": False, "reason": "gate_zero_damage"}
    if has_ko_cand and not cand.get("is_attack") and not cand.get("can_ko"):
        return {"allowed": False, "reason": "gate_ko_available_non_attack"}
    return {"allowed": True, "reason": ""}


def compute_hybrid_scores(
    cands: List[dict], model: DecisionTreeRanker, bonus_ratio: float,
) -> List[dict]:
    """Score candidates with safety-gated hybrid."""
    has_legal_attack = any(c.get("has_legal_attack") for c in cands)
    has_ko = any(c.get("can_ko") for c in cands)

    ml_scores = [model.score(c) for c in cands]
    ml_min = min(ml_scores) if ml_scores else 0
    ml_max = max(ml_scores) if ml_scores else 1
    ml_range = ml_max - ml_min if ml_max > ml_min else 1.0

    results = []
    for i, c in enumerate(cands):
        rule_score = c.get("rule_score", 0)
        ml_raw = ml_scores[i]
        normalized = (ml_raw - ml_min) / ml_range

        gate = apply_safety_gate(c, has_legal_attack, has_ko)
        ml_bonus = bonus_ratio * _ML_BONUS_SCALE * normalized if gate["allowed"] else 0.0
        hybrid = rule_score + ml_bonus

        results.append({
            **c,
            "ml_score": round(ml_raw, 4),
            "ml_bonus": round(ml_bonus, 4),
            "hybrid_score": round(hybrid, 4),
            "gate_allowed": gate["allowed"],
            "gate_reason": gate["reason"],
        })
    return results


def evaluate_hybrid(
    model: DecisionTreeRanker,
    eval_data: List[dict],
    bonus_ratio: float,
    output_path: str,
) -> dict:
    groups = group_by_decision(eval_data)
    stats = {
        "decisions": len(groups), "candidates": len(eval_data),
        "rule_hybrid_top1_agree": 0, "hybrid_changed": 0,
        "hybrid_end_legal_attack": 0, "hybrid_zero_damage": 0,
        "hybrid_miss_ko": 0,
        "gate_blocked_total": 0, "gate_blocked_end": 0,
        "gate_blocked_zero": 0, "gate_blocked_ko_risk": 0,
        "rule_reward_sum": 0.0, "hybrid_reward_sum": 0.0,
        "hybrid_type_dist": {}, "rule_type_dist": {},
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out_f:
        for key, cands in groups.items():
            scored = compute_hybrid_scores(cands, model, bonus_ratio)

            rule_sorted = sorted(scored, key=lambda c: c.get("rule_score", 0), reverse=True)
            hybrid_sorted = sorted(scored, key=lambda c: c.get("hybrid_score", 0), reverse=True)

            rule_top = rule_sorted[0] if rule_sorted else {}
            hybrid_top = hybrid_sorted[0] if hybrid_sorted else {}

            rule_idx = rule_top.get("action_index")
            hybrid_idx = hybrid_top.get("action_index")

            if rule_idx == hybrid_idx:
                stats["rule_hybrid_top1_agree"] += 1
            else:
                stats["hybrid_changed"] += 1

            rt = str(rule_top.get("action_type", ""))
            ht = str(hybrid_top.get("action_type", ""))
            stats["rule_type_dist"][rt] = stats["rule_type_dist"].get(rt, 0) + 1
            stats["hybrid_type_dist"][ht] = stats["hybrid_type_dist"].get(ht, 0) + 1

            if hybrid_top.get("is_end") and any(c.get("has_legal_attack") for c in cands):
                stats["hybrid_end_legal_attack"] += 1
            if hybrid_top.get("is_zero_damage_attack"):
                stats["hybrid_zero_damage"] += 1
            if any(c.get("can_ko") for c in cands) and not hybrid_top.get("is_attack"):
                stats["hybrid_miss_ko"] += 1

            for c in scored:
                if not c.get("gate_allowed"):
                    stats["gate_blocked_total"] += 1
                    r = c.get("gate_reason", "")
                    if "end" in r:
                        stats["gate_blocked_end"] += 1
                    elif "zero" in r:
                        stats["gate_blocked_zero"] += 1
                    elif "ko" in r:
                        stats["gate_blocked_ko_risk"] += 1

            rule_reward = rule_top.get("reward", 0) or 0
            hybrid_reward = hybrid_top.get("reward", 0) or 0
            stats["rule_reward_sum"] += rule_reward
            stats["hybrid_reward_sum"] += hybrid_reward

            for rank, c in enumerate(hybrid_sorted):
                rule_rank = next((i+1 for i, rc in enumerate(rule_sorted)
                                 if rc.get("action_index") == c.get("action_index")), len(cands))
                out_f.write(json.dumps({
                    "game_id": c.get("game_id"), "decision_id": c.get("decision_id"),
                    "turn": c.get("turn"), "action_index": c.get("action_index"),
                    "action_type": c.get("action_type"), "selected": c.get("selected"),
                    "rule_score": c.get("rule_score"), "rule_rank": rule_rank,
                    "ml_score": c.get("ml_score"), "ml_bonus": c.get("ml_bonus"),
                    "hybrid_score": c.get("hybrid_score"), "hybrid_rank": rank + 1,
                    "rule_selected": c.get("selected"),
                    "hybrid_selected": rank == 0,
                    "gate_allowed": c.get("gate_allowed"), "gate_reason": c.get("gate_reason"),
                    "is_attack": c.get("is_attack"), "can_ko": c.get("can_ko"),
                    "is_zero_damage_attack": c.get("is_zero_damage_attack"),
                    "is_end": c.get("is_end"), "has_legal_attack": c.get("has_legal_attack"),
                    "game_result": c.get("game_result"), "reward": c.get("reward"),
                }, ensure_ascii=False) + "\n")

    d = stats["decisions"] or 1
    stats["rule_hybrid_agree_rate"] = round(stats["rule_hybrid_top1_agree"] / d, 4)
    stats["hybrid_changed_rate"] = round(stats["hybrid_changed"] / d, 4)
    stats["rule_reward_avg"] = round(stats["rule_reward_sum"] / d, 4)
    stats["hybrid_reward_avg"] = round(stats["hybrid_reward_sum"] / d, 4)
    stats["reward_delta"] = round(stats["hybrid_reward_sum"] - stats["rule_reward_sum"], 4)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Safety-gated ML hybrid evaluation")
    parser.add_argument("--train", required=True)
    parser.add_argument("--eval", required=True)
    parser.add_argument("--output", default="artifacts/ml_hybrid_safety_eval.jsonl")
    parser.add_argument("--summary", default="artifacts/ml_hybrid_safety_summary.json")
    parser.add_argument("--ml-bonus-ratio", type=float, default=0.10)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--min-leaf", type=int, default=20)
    args = parser.parse_args()

    print(f"Loading train data from {args.train}...")
    train_data = load_jsonl(args.train)
    print(f"  {len(train_data)} rows")

    print(f"\nTraining DecisionTreeRanker (depth={args.max_depth})...")
    model = DecisionTreeRanker(
        feature_list=_NO_RULE_FEATURES,
        max_depth=args.max_depth, min_samples_leaf=args.min_leaf,
    )
    model.train(train_data)

    print(f"\nTop features:")
    for name, count in model.top_features(8):
        print(f"  {name}: {count} splits")

    print(f"\nLoading eval data from {args.eval}...")
    eval_data = load_jsonl(args.eval)
    print(f"  {len(eval_data)} rows")

    print(f"\nEvaluating hybrid (bonus_ratio={args.ml_bonus_ratio})...")
    stats = evaluate_hybrid(model, eval_data, args.ml_bonus_ratio, args.output)

    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nHybrid Safety Eval Summary:")
    print(f"  Decisions: {stats['decisions']}")
    print(f"  Rule/Hybrid agree: {stats['rule_hybrid_agree_rate']:.1%}")
    print(f"  Changed decisions: {stats['hybrid_changed']} ({stats['hybrid_changed_rate']:.1%})")
    print(f"  End+legal_attack: {stats['hybrid_end_legal_attack']}")
    print(f"  Zero damage: {stats['hybrid_zero_damage']}")
    print(f"  Miss KO: {stats['hybrid_miss_ko']}")
    print(f"  Gate blocked: {stats['gate_blocked_total']}")
    print(f"  Reward delta: {stats['reward_delta']}")
    print(f"Saved to {args.output} + {args.summary}")


if __name__ == "__main__":
    main()
