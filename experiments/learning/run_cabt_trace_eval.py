"""
CLI for cabt trace evaluation.

Usage:
  python experiments/learning/run_cabt_trace_eval.py \
      --agent main.py --deck deck.csv --n 10 \
      --use-advisor --label test_run

  python experiments/learning/run_cabt_trace_eval.py \
      --agent main.py --deck deck.csv --dry-run --label ci_check
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.learning.cabt_trace_eval_runner import execute_trace_eval


def main():
    parser = argparse.ArgumentParser(description="Run cabt trace evaluation")
    parser.add_argument("--agent", default="main.py")
    parser.add_argument("--deck", default="deck.csv")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--use-advisor", action="store_true")
    parser.add_argument("--weights", default="")
    parser.add_argument("--fallback-weights", default="")
    parser.add_argument("--output-base", default="experiments/learning/trace_eval_runs")
    parser.add_argument("--label", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=== cabt Trace Evaluation ===")
    print("Agent: %s" % args.agent)
    print("Deck: %s" % args.deck)
    print("Games: %d" % args.n)
    print("Advisor: %s" % ("ON" if args.use_advisor else "OFF"))
    print("Dry run: %s" % args.dry_run)
    print()

    result = execute_trace_eval(
        agent=args.agent, deck=args.deck, n=args.n,
        use_advisor=args.use_advisor,
        weights_path=args.weights,
        fallback_path=args.fallback_weights,
        output_base=args.output_base,
        label=args.label,
        dry_run=args.dry_run,
    )

    print("Run dir: %s" % result["run_dir"])
    print("Metadata: %s" % result["metadata"])

    sp = result.get("self_play", {})
    print("Self-play returncode: %s" % sp.get("returncode", "?"))

    analysis = result.get("analysis", {})
    if analysis.get("trace_entries"):
        print("Trace entries: %d" % analysis["trace_entries"])
    if analysis.get("error"):
        print("Analysis error: %s" % analysis["error"])

    print("\nDone.")


if __name__ == "__main__":
    main()
