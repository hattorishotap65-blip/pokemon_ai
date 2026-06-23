"""
ML shadow scoring — train action ranker and evaluate agreement with rule policy.

No behavior change. ML scores are logged alongside rule scores for comparison.

Usage:
  python experiments/ml_shadow_scoring.py \
      --train artifacts/action_features_train_50g.jsonl \
      --eval artifacts/action_features_eval_100g.jsonl \
      --output artifacts/ml_shadow_eval_100g.jsonl \
      --summary artifacts/ml_shadow_summary.json
"""
from __future__ import annotations
import argparse
import json
import math
import os
import random
import sys
from typing import Dict, List, Tuple

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

_NUMERIC_FEATURES = [
    "action_type", "rule_score", "candidate_rank", "legal_action_count",
    "active_hp", "active_energy", "active_energy_needed",
    "opponent_active_hp", "bench_size",
    "prize_remaining", "opponent_prize_remaining", "prize_diff",
    "deck_count", "hand_count",
]
_BOOL_FEATURES = [
    "has_legal_attack", "is_attack", "can_ko", "is_zero_damage_attack",
    "attack_energy_ready", "is_attach", "attach_to_active", "attach_to_bench",
    "attach_enables_attack", "active_attach_would_enable",
    "is_evolve", "evolve_to_main_attacker", "evolve_to_engine",
    "is_play", "is_ability", "is_retreat", "is_end", "late_game",
]
ALL_FEATURES = _NUMERIC_FEATURES + _BOOL_FEATURES


def _to_feature_vec(row: dict) -> List[float]:
    vec = []
    for k in _NUMERIC_FEATURES:
        v = row.get(k, 0)
        if v is None or v is False:
            v = 0
        elif v is True:
            v = 1
        vec.append(float(v))
    for k in _BOOL_FEATURES:
        v = row.get(k, False)
        if v is True:
            vec.append(1.0)
        elif v is False or v is None:
            vec.append(0.0)
        else:
            vec.append(float(v))
    return vec


def load_jsonl(path: str, max_lines: int = 0) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
            if max_lines > 0 and len(rows) >= max_lines:
                break
    return rows


def _sigmoid(x: float) -> float:
    x = max(-50.0, min(50.0, x))
    return 1.0 / (1.0 + math.exp(-x))


class LinearRanker:
    def __init__(self):
        self.weights: List[float] = []
        self.bias: float = 0.0

    def train(self, data: List[dict], epochs: int = 5, lr: float = 0.01,
              l2: float = 0.001, seed: int = 42):
        n_feat = len(ALL_FEATURES)
        self.weights = [0.0] * n_feat
        self.bias = 0.0
        rng = random.Random(seed)

        samples = [(self._to_x(r), 1.0 if r.get("selected") else 0.0) for r in data]
        for epoch in range(epochs):
            rng.shuffle(samples)
            total_loss = 0.0
            for x, y in samples:
                z = sum(w * xi for w, xi in zip(self.weights, x)) + self.bias
                p = _sigmoid(z)
                err = p - y
                total_loss += -y * math.log(max(p, 1e-12)) - (1 - y) * math.log(max(1 - p, 1e-12))
                for i in range(n_feat):
                    self.weights[i] -= lr * (err * x[i] + l2 * self.weights[i])
                self.bias -= lr * err
            avg = total_loss / len(samples) if samples else 0
            print(f"  epoch {epoch+1}/{epochs} loss={avg:.4f}")

    def score(self, row: dict) -> float:
        x = self._to_x(row)
        return sum(w * xi for w, xi in zip(self.weights, x)) + self.bias

    def _to_x(self, row: dict) -> List[float]:
        return _to_feature_vec(row)

    def top_features(self, n: int = 10) -> List[Tuple[str, float]]:
        pairs = list(zip(ALL_FEATURES, self.weights))
        pairs.sort(key=lambda p: abs(p[1]), reverse=True)
        return [(k, round(v, 4)) for k, v in pairs[:n]]


def group_by_decision(rows: List[dict]) -> Dict[str, List[dict]]:
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        key = f"{r.get('game_id', 0)}-{r.get('turn', 0)}"
        groups.setdefault(key, []).append(r)
    return groups


def evaluate_shadow(model: LinearRanker, eval_data: List[dict], output_path: str) -> dict:
    groups = group_by_decision(eval_data)

    stats = {
        "decisions": len(groups), "candidates": len(eval_data),
        "top1_agree": 0, "top3_agree": 0,
        "ml_end_top1": 0, "ml_end_top1_with_legal_attack": 0,
        "ml_miss_ko": 0, "ml_zero_damage_top1": 0,
        "ml_type_dist": {}, "rule_type_dist": {},
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out_f:
        for key, cands in groups.items():
            scored = []
            for c in cands:
                ms = model.score(c)
                scored.append((ms, c))

            scored.sort(key=lambda x: x[0], reverse=True)
            rule_sorted = sorted(cands, key=lambda c: c.get("rule_score", 0), reverse=True)

            ml_top1 = scored[0][1] if scored else {}
            rule_top1 = rule_sorted[0] if rule_sorted else {}

            ml_top1_idx = ml_top1.get("action_index")
            rule_top1_idx = rule_top1.get("action_index")

            if ml_top1_idx == rule_top1_idx:
                stats["top1_agree"] += 1

            ml_top3_idxs = {s[1].get("action_index") for s in scored[:3]}
            if rule_top1_idx in ml_top3_idxs:
                stats["top3_agree"] += 1

            ml_type = str(ml_top1.get("action_type", ""))
            rule_type = str(rule_top1.get("action_type", ""))
            stats["ml_type_dist"][ml_type] = stats["ml_type_dist"].get(ml_type, 0) + 1
            stats["rule_type_dist"][rule_type] = stats["rule_type_dist"].get(rule_type, 0) + 1

            if ml_top1.get("is_end"):
                stats["ml_end_top1"] += 1
                if ml_top1.get("has_legal_attack"):
                    stats["ml_end_top1_with_legal_attack"] += 1

            if any(c.get("can_ko") for c in cands) and not ml_top1.get("is_attack"):
                stats["ml_miss_ko"] += 1

            if ml_top1.get("is_zero_damage_attack"):
                stats["ml_zero_damage_top1"] += 1

            for rank, (ms, c) in enumerate(scored):
                rule_rank = next((i + 1 for i, rc in enumerate(rule_sorted)
                                 if rc.get("action_index") == c.get("action_index")), len(cands))
                out_f.write(json.dumps({
                    "game_id": c.get("game_id"),
                    "turn": c.get("turn"),
                    "action_index": c.get("action_index"),
                    "action_type": c.get("action_type"),
                    "selected": c.get("selected"),
                    "rule_score": c.get("rule_score"),
                    "rule_rank": rule_rank,
                    "ml_score": round(ms, 4),
                    "ml_rank": rank + 1,
                    "rule_selected": c.get("selected"),
                    "ml_selected": rank == 0,
                    "rule_reason": c.get("rule_reason", ""),
                    "game_result": c.get("game_result", ""),
                    "reward": c.get("reward", 0),
                    "is_attack": c.get("is_attack"),
                    "can_ko": c.get("can_ko"),
                    "is_zero_damage_attack": c.get("is_zero_damage_attack"),
                    "is_attach": c.get("is_attach"),
                    "attach_enables_attack": c.get("attach_enables_attack"),
                    "is_end": c.get("is_end"),
                }, ensure_ascii=False) + "\n")

    d = stats["decisions"] or 1
    stats["top1_agreement_rate"] = round(stats["top1_agree"] / d, 4)
    stats["top3_agreement_rate"] = round(stats["top3_agree"] / d, 4)
    return stats


def main():
    parser = argparse.ArgumentParser(description="ML shadow scoring")
    parser.add_argument("--train", required=True)
    parser.add_argument("--eval", required=True)
    parser.add_argument("--output", default="artifacts/ml_shadow_eval.jsonl")
    parser.add_argument("--summary", default="artifacts/ml_shadow_summary.json")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--max-train", type=int, default=200000)
    args = parser.parse_args()

    print(f"Loading train data from {args.train}...")
    train_data = load_jsonl(args.train, args.max_train)
    print(f"  {len(train_data)} rows")

    print(f"\nTraining LinearRanker...")
    model = LinearRanker()
    model.train(train_data, epochs=args.epochs, lr=args.lr)

    print(f"\nTop features:")
    for name, w in model.top_features(10):
        print(f"  {name}: {w}")

    print(f"\nLoading eval data from {args.eval}...")
    eval_data = load_jsonl(args.eval)
    print(f"  {len(eval_data)} rows")

    print(f"\nEvaluating shadow scores...")
    stats = evaluate_shadow(model, eval_data, args.output)

    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nShadow Scoring Summary:")
    print(f"  Decisions: {stats['decisions']}")
    print(f"  Candidates: {stats['candidates']}")
    print(f"  Top1 agreement: {stats['top1_agreement_rate']:.1%}")
    print(f"  Top3 agreement: {stats['top3_agreement_rate']:.1%}")
    print(f"  ML End top1: {stats['ml_end_top1']}")
    print(f"  ML End+legal_attack: {stats['ml_end_top1_with_legal_attack']}")
    print(f"  ML miss KO: {stats['ml_miss_ko']}")
    print(f"  ML zero_damage top1: {stats['ml_zero_damage_top1']}")
    print(f"Saved to {args.output} + {args.summary}")


if __name__ == "__main__":
    main()
