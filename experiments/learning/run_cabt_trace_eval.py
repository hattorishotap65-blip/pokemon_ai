"""
CLI for cabt trace evaluation.

Usage:
  python experiments/learning/run_cabt_trace_eval.py \
      --run-dir /tmp/eval_run --agent main.py --deck deck.csv --n 10

  python experiments/learning/run_cabt_trace_eval.py \
      --run-dir /tmp/eval_run --skip-command --label ci_check

  python experiments/learning/run_cabt_trace_eval.py \
      --run-dir /tmp/eval_run --use-advisor --label advisor_test
"""
from __future__ import annotations
import argparse
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.learning.cabt_trace_eval_runner import execute_trace_eval


def main():
    parser = argparse.ArgumentParser(description="Run cabt trace evaluation")
    parser.add_argument("--run-dir", default="", help="Explicit run directory (created if missing)")
    parser.add_argument("--agent", default="main.py")
    parser.add_argument("--deck", default="deck.csv")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--use-advisor", action="store_true")
    parser.add_argument("--weights", default="")
    parser.add_argument("--fallback-weights", default="")
    parser.add_argument("--output-base", default="experiments/learning/trace_eval_runs")
    parser.add_argument("--label", default="")
    parser.add_argument("--skip-command", action="store_true",
                        help="Skip cabt execution, only create run dir and analysis outputs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Alias for --skip-command")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="Custom cabt command after -- (overrides --agent/--deck/--n)")
    args = parser.parse_args()

    skip = args.skip_command or args.dry_run

    custom_command = None
    if args.command:
        # Strip leading '--' if present
        cmd = args.command
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        if cmd:
            custom_command = cmd

    print("=== cabt Trace Evaluation ===")
    print("Agent: %s" % args.agent)
    print("Deck: %s" % args.deck)
    print("Games: %d" % args.n)
    print("Advisor: %s" % ("ON" if args.use_advisor else "OFF"))
    print("Skip command: %s" % skip)
    print()

    result = execute_trace_eval(
        command=custom_command,
        agent=args.agent, deck=args.deck, n=args.n,
        use_advisor=args.use_advisor,
        weights_path=args.weights,
        fallback_path=args.fallback_weights,
        output_base=args.output_base,
        run_dir=args.run_dir,
        label=args.label,
        skip_command=skip,
    )

    print("Run dir: %s" % result["run_dir"])
    print("Metadata: %s" % result["metadata"])

    cmd = result.get("command_result", {})
    print("Command returncode: %s (skipped=%s)" % (cmd.get("returncode", "?"), cmd.get("skipped", "?")))

    analysis = result.get("analysis", {})
    print("Trace entries: %d" % analysis.get("trace_entries", 0))
    if analysis.get("error"):
        print("Analysis error: %s" % analysis["error"])

    print("\nDone.")


if __name__ == "__main__":
    main()
