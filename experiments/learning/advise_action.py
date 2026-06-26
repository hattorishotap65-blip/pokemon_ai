"""
CLI to evaluate advisor behavior on sample logs.

Usage:
  python experiments/learning/advise_action.py \
      --logs experiments/learning/sample_logs/raging_ogerpon_sample.jsonl \
      --weights experiments/learning/params/raging_ogerpon_default.json
"""
from __future__ import annotations
import argparse
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.learning.schema import load_logs
from experiments.learning.weight_profile import load_weight_profile
from experiments.learning.decision_advisor import rank_candidates


def main():
    parser = argparse.ArgumentParser(description="Evaluate advisor on sample logs")
    parser.add_argument("--logs", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--show-mismatches", type=int, default=3)
    args = parser.parse_args()

    logs = load_logs(args.logs)
    weights = load_weight_profile(args.weights)

    print("Logs: %d entries" % len(logs))
    print("Weights: %d keys" % len(weights))
    print()

    matches = 0
    total = 0
    rank_sum = 0
    mismatches = []

    for entry in logs:
        actions = entry.get("legal_actions", [])
        state = entry.get("state", {})
        chosen_id = entry.get("chosen_action_id", "")
        if not actions or not chosen_id:
            continue

        ranked = rank_candidates(state, actions, weights)
        if not ranked:
            continue

        total += 1
        predicted_id = ranked[0]["action_id"]

        chosen_rank = -1
        for r in ranked:
            if r["action_id"] == chosen_id:
                chosen_rank = ranked.index(r) + 1
                break

        if chosen_rank > 0:
            rank_sum += chosen_rank

        if predicted_id == chosen_id:
            matches += 1
        else:
            mismatches.append({
                "match_id": entry.get("match_id", "?"),
                "turn": entry.get("turn", "?"),
                "chosen": chosen_id,
                "predicted": predicted_id,
                "chosen_rank": chosen_rank,
            })

    print("=== Advisor Results ===")
    print("Total entries: %d" % total)
    print("Top-1 matches: %d" % matches)
    print("Top-1 accuracy: %.1f%%" % (matches / total * 100 if total else 0))
    print("Avg chosen rank: %.2f" % (rank_sum / total if total else 0))

    if mismatches and args.show_mismatches > 0:
        print("\n=== Sample Mismatches ===")
        for m in mismatches[:args.show_mismatches]:
            print("  match=%s turn=%s chosen=%s predicted=%s rank=%s" % (
                m["match_id"], m["turn"], m["chosen"], m["predicted"], m["chosen_rank"]))


if __name__ == "__main__":
    main()
