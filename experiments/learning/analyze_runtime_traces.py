"""
CLI to analyze runtime advisor trace files.

Usage:
  python experiments/learning/analyze_runtime_traces.py \
      --trace experiments/learning/runtime_traces/advisor_trace.jsonl \
      --report experiments/learning/runtime_traces/trace_report.md \
      --summary experiments/learning/runtime_traces/trace_summary.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.learning.trace_analyzer import (
    load_traces, analyze_traces, format_report, find_override_cases,
)


def main():
    parser = argparse.ArgumentParser(description="Analyze runtime advisor traces")
    parser.add_argument("--trace", required=True, help="Trace JSONL file")
    parser.add_argument("--report", "--out-md", default="", help="Output Markdown report path")
    parser.add_argument("--summary", "--out-json", default="", help="Output JSON summary path")
    args = parser.parse_args()

    entries = load_traces(args.trace)
    print("Loaded %d trace entries from %s" % (len(entries), args.trace))

    summary = analyze_traces(entries)

    print("\n=== Summary ===")
    print("Total decisions: %d" % summary["total"])
    print("Advisor used: %d (%.1f%%)" % (summary["advisor_used"], summary["advisor_used_rate"] * 100))
    print("Fallback: %d" % summary["fallback_count"])
    print("Override: %d (%.1f%%)" % (summary["override_count"], summary["override_rate"] * 100))
    print("Avg top score: %.2f" % summary["avg_advisor_top_score"])

    reasons = summary.get("fallback_reasons", {})
    if reasons:
        print("\nFallback reasons:")
        for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
            print("  %s: %d" % (r, c))

    overrides = find_override_cases(entries)
    if overrides:
        print("\nOverride cases: %d" % len(overrides))

    if args.report:
        report = format_report(summary, overrides)
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        print("\nSaved report to %s" % args.report)

    if args.summary:
        os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
        with open(args.summary, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print("Saved summary to %s" % args.summary)


if __name__ == "__main__":
    main()
