"""
Simple imitation-style weight updater.

Adjusts weights so that the human-chosen action scores higher
than other candidates.

Usage:
  python experiments/learning/train_weights.py \
      --logs experiments/learning/sample_logs/raging_ogerpon_sample.jsonl \
      --params experiments/learning/params/raging_ogerpon_default.json \
      --out experiments/learning/params/raging_ogerpon_learned.json \
      --report experiments/learning/reports/latest_report.md
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Dict, List

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.learning.schema import load_logs
from experiments.learning.action_features import extract_action_features
from experiments.learning.evaluator import (
    load_weights, save_weights, evaluate_log_entry, rank_actions,
)
from experiments.learning.report import generate_report


def compute_learning_multiplier(entry: dict) -> float:
    """Compute a learning rate multiplier based on game outcome."""
    result = entry.get("result", {})
    m = 1.0

    win = result.get("win")
    if win is True:
        m *= 1.2
    elif win is False:
        m *= 0.7

    if result.get("starting_hand_bricked", False):
        m *= 0.5

    prizes = result.get("prizes_taken")
    if prizes is not None:
        if prizes >= 5:
            m *= 1.1
        elif prizes <= 2 and not win:
            m *= 0.8

    turns = result.get("turns_to_win")
    if win and turns is not None and 0 < turns <= 5:
        m *= 1.1

    return max(0.2, min(2.0, m))


def train(logs: List[dict], weights: Dict[str, float],
          epochs: int = 5, lr: float = 0.05) -> Dict[str, float]:
    """Train weights to match human choices via perceptron-style updates."""
    w = dict(weights)

    for epoch in range(epochs):
        for entry in logs:
            actions = entry.get("legal_actions", [])
            state = entry.get("state", {})
            chosen_id = entry.get("chosen_action_id", "")

            if not actions or not chosen_id:
                continue

            ranked = rank_actions(actions, state, w)
            predicted_id = ranked[0][0] if ranked else ""

            if predicted_id == chosen_id:
                continue

            chosen_action = None
            predicted_action = None
            for a in actions:
                if a.get("id") == chosen_id:
                    chosen_action = a
                if a.get("id") == predicted_id:
                    predicted_action = a

            if not chosen_action or not predicted_action:
                continue

            chosen_features = extract_action_features(chosen_action, state, actions)
            predicted_features = extract_action_features(predicted_action, state, actions)

            effective_lr = lr * compute_learning_multiplier(entry)

            for name, value in chosen_features.items():
                w[name] = w.get(name, 0.0) + effective_lr * value

            for name, value in predicted_features.items():
                w[name] = w.get(name, 0.0) - effective_lr * value

    return w


def evaluate_all(logs: List[dict], weights: Dict[str, float]) -> dict:
    """Evaluate all logs and return aggregate stats."""
    matches = 0
    total = 0
    rank_sum = 0

    for entry in logs:
        result = evaluate_log_entry(entry, weights)
        if result["rank"] < 0:
            continue
        total += 1
        if result["match"]:
            matches += 1
        rank_sum += result["rank"]

    return {
        "total": total,
        "matches": matches,
        "accuracy": round(matches / total, 4) if total else 0.0,
        "avg_rank": round(rank_sum / total, 2) if total else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Train action weights from human logs")
    parser.add_argument("--logs", required=True)
    parser.add_argument("--params", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.05)
    args = parser.parse_args()

    print("Loading logs from %s..." % args.logs)
    logs = load_logs(args.logs)
    print("  %d valid entries" % len(logs))

    print("Loading weights from %s..." % args.params)
    weights_before = load_weights(args.params)
    print("  %d weight keys" % len(weights_before))

    print("\nBefore training:")
    stats_before = evaluate_all(logs, weights_before)
    print("  accuracy: %.1f%% (%d/%d), avg rank: %.2f" % (
        stats_before["accuracy"] * 100, stats_before["matches"],
        stats_before["total"], stats_before["avg_rank"]))

    print("\nTraining (epochs=%d, lr=%.3f)..." % (args.epochs, args.lr))
    weights_after = train(logs, weights_before, epochs=args.epochs, lr=args.lr)

    print("\nAfter training:")
    stats_after = evaluate_all(logs, weights_after)
    print("  accuracy: %.1f%% (%d/%d), avg rank: %.2f" % (
        stats_after["accuracy"] * 100, stats_after["matches"],
        stats_after["total"], stats_after["avg_rank"]))

    save_weights(weights_after, args.out)
    print("\nSaved learned weights to %s" % args.out)

    if args.report:
        report = generate_report(logs, weights_before, weights_after,
                                 stats_before, stats_after)
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        print("Saved report to %s" % args.report)


if __name__ == "__main__":
    main()
