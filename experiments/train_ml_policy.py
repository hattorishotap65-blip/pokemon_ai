"""
Offline pairwise linear ranker for ML policy.

Trains from JSONL candidate-action examples produced by
collect_ml_training_data.py. Outputs disabled-by-default weights
to artifacts/.

Usage:
  python experiments/train_ml_policy.py \
      --input artifacts/ml_training_data_full.jsonl \
      --output artifacts/ml_policy_weights_trained.json \
      --epochs 5 --lr 0.01
"""
from __future__ import annotations
import argparse
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)


# ── data loading ──────────────────────────────────────────────────

def load_examples(path: str, max_examples: int = 0) -> List[dict]:
    examples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                examples.append(json.loads(line))
            except Exception:
                continue
            if max_examples > 0 and len(examples) >= max_examples:
                break
    return examples


def group_by_decision(examples: List[dict]) -> Dict[str, List[dict]]:
    groups: Dict[str, List[dict]] = {}
    for ex in examples:
        did = ex.get("decision_id", "")
        if not did:
            continue
        groups.setdefault(did, []).append(ex)
    return groups


# ── feature flattening ───────────────────────────────────────────

_ONEHOT_FIELDS = {"best_plan_type", "option_class"}


def flatten_numeric_features(features: dict) -> Dict[str, float]:
    if not isinstance(features, dict):
        return {}
    result: Dict[str, float] = {}
    for k, v in features.items():
        if isinstance(v, bool):
            result[k] = 1.0 if v else 0.0
        elif isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v):
            result[k] = float(v)
        elif isinstance(v, str) and v and k in _ONEHOT_FIELDS:
            result[f"{k}={v}"] = 1.0
    return result


# ── scoring ───────────────────────────────────────────────────────

def score_features(features: Dict[str, float], weights: Dict[str, float]) -> float:
    s = 0.0
    for k, w in weights.items():
        v = features.get(k, 0.0)
        s += v * w
    return s


# ── training ──────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    x = max(-50.0, min(50.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def train_pairwise_ranker(
    groups: Dict[str, List[dict]],
    epochs: int = 5,
    lr: float = 0.01,
    seed: int = 42,
    l2: float = 0.001,
) -> Dict[str, float]:
    """Train pairwise linear ranker via SGD."""
    rng = random.Random(seed)

    pairs: List[Tuple[Dict[str, float], Dict[str, float]]] = []
    for did, candidates in groups.items():
        positives = [c for c in candidates if c.get("selected")]
        negatives = [c for c in candidates if not c.get("selected")]
        if not positives or not negatives:
            continue
        for pos in positives:
            pf = flatten_numeric_features(pos.get("features") or {})
            for neg in negatives:
                nf = flatten_numeric_features(neg.get("features") or {})
                pairs.append((pf, nf))

    if not pairs:
        return {}

    all_keys: set = set()
    for pf, nf in pairs:
        all_keys.update(pf.keys())
        all_keys.update(nf.keys())

    weights: Dict[str, float] = {k: 0.0 for k in all_keys}

    for epoch in range(epochs):
        rng.shuffle(pairs)
        total_loss = 0.0
        for pf, nf in pairs:
            diff = score_features(pf, weights) - score_features(nf, weights)
            prob = _sigmoid(diff)
            grad_scale = prob - 1.0  # d/dw of -log(sigmoid(diff))
            total_loss += -math.log(max(prob, 1e-12))

            for k in all_keys:
                d = pf.get(k, 0.0) - nf.get(k, 0.0)
                weights[k] -= lr * (grad_scale * d + l2 * weights[k])

        avg_loss = total_loss / len(pairs) if pairs else 0.0
        print(f"  epoch {epoch+1}/{epochs}  loss={avg_loss:.4f}  pairs={len(pairs)}")

    return weights


# ── evaluation ────────────────────────────────────────────────────

def evaluate_ranker(
    groups: Dict[str, List[dict]],
    weights: Dict[str, float],
) -> dict:
    top1_correct = 0
    total_decisions = 0
    rank_sum = 0
    margin_sum = 0.0

    for did, candidates in groups.items():
        positives = [c for c in candidates if c.get("selected")]
        if not positives:
            continue

        scored = []
        for c in candidates:
            feat = flatten_numeric_features(c.get("features") or {})
            s = score_features(feat, weights)
            scored.append((s, c.get("selected", False)))

        scored.sort(key=lambda x: x[0], reverse=True)

        total_decisions += 1
        if scored[0][1]:
            top1_correct += 1

        for rank, (s, sel) in enumerate(scored):
            if sel:
                rank_sum += rank + 1
                neg_scores = [sc for sc, sl in scored if not sl]
                best_neg = max(neg_scores) if neg_scores else s
                margin_sum += s - best_neg
                break

    return {
        "decisions": total_decisions,
        "top1_accuracy": round(top1_correct / total_decisions, 4) if total_decisions else 0.0,
        "avg_selected_rank": round(rank_sum / total_decisions, 2) if total_decisions else 0.0,
        "selected_score_margin_avg": round(margin_sum / total_decisions, 4) if total_decisions else 0.0,
    }


# ── output ────────────────────────────────────────────────────────

def save_weights(path: str, weights: Dict[str, float], metrics: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = {
        "enabled": False,
        "mode": "trained_offline",
        "model_type": "pairwise_linear_ranker",
        "weights": {k: round(v, 6) for k, v in sorted(weights.items())},
        "metrics": metrics,
        "notes": "offline trained, not used by default",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_weights(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train ML policy from JSONL")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="artifacts/ml_policy_weights_trained.json")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=0.001)
    parser.add_argument("--max-examples", type=int, default=50000)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"Loading data from {args.input}...")
    examples = load_examples(args.input, args.max_examples)
    print(f"  {len(examples)} examples loaded")

    groups = group_by_decision(examples)
    valid_groups = {k: v for k, v in groups.items()
                    if any(c.get("selected") for c in v)
                    and any(not c.get("selected") for c in v)}
    print(f"  {len(groups)} decisions, {len(valid_groups)} with both pos+neg")

    if not valid_groups:
        print("ERROR: no valid training groups found. Need --include-unselected data.")
        sys.exit(1)

    # Split train / validation
    rng = random.Random(args.seed)
    keys = list(valid_groups.keys())
    rng.shuffle(keys)
    split = int(len(keys) * (1.0 - args.validation_ratio))
    train_keys = keys[:split]
    valid_keys = keys[split:]

    train_groups = {k: valid_groups[k] for k in train_keys}
    valid_groups_eval = {k: valid_groups[k] for k in valid_keys}

    print(f"\nTraining on {len(train_groups)} decisions, validating on {len(valid_groups_eval)}...")
    weights = train_pairwise_ranker(train_groups, args.epochs, args.lr, args.seed, args.l2)

    print(f"\n--- Train metrics ---")
    train_metrics = evaluate_ranker(train_groups, weights)
    for k, v in train_metrics.items():
        print(f"  {k}: {v}")

    print(f"\n--- Validation metrics ---")
    valid_metrics = evaluate_ranker(valid_groups_eval, weights)
    for k, v in valid_metrics.items():
        print(f"  {k}: {v}")

    metrics = {
        "train": train_metrics,
        "validation": valid_metrics,
        "epochs": args.epochs,
        "lr": args.lr,
        "l2": args.l2,
        "total_examples": len(examples),
        "total_decisions": len(groups),
        "valid_decisions": len(valid_groups),
    }

    save_weights(args.output, weights, metrics)
    print(f"\nWeights saved to {args.output}")
    print(f"  Features: {len(weights)}")
    top5 = sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
    print(f"  Top 5 by |weight|: {[(k, round(v, 4)) for k, v in top5]}")


if __name__ == "__main__":
    main()
