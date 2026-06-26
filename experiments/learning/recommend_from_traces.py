"""
CLI to generate tuning recommendations from advisor traces.

Usage:
  python experiments/learning/recommend_from_traces.py \
      --trace experiments/learning/sample_traces/sample_tuning_trace.jsonl \
      --report experiments/learning/runtime_traces/tuning_report.md \
      --summary experiments/learning/runtime_traces/tuning_summary.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_DIR, "..", ".."))
sys.path.insert(0, _REPO)

from experiments.learning.trace_analyzer import load_traces, analyze_traces
from experiments.learning.trace_recommender import (
    build_tuning_recommendations, render_recommendation_report,
)


def main():
    parser = argparse.ArgumentParser(description="Generate tuning recommendations from traces")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--report", "--out-md", default="")
    parser.add_argument("--summary", "--out-json", default="")
    args = parser.parse_args()

    entries = load_traces(args.trace)
    print("Loaded %d trace entries" % len(entries))

    summary = analyze_traces(entries)
    recs = build_tuning_recommendations(entries, summary)

    print("\n=== Recommendations ===")
    for r in recs.get("recommendations", []):
        print("  [%s] %s: %s" % (r["priority"].upper(), r["issue"], r["detail"]))

    if args.report:
        md = render_recommendation_report(recs)
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(md)
        print("\nSaved report to %s" % args.report)

    if args.summary:
        os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
        with open(args.summary, "w", encoding="utf-8") as f:
            json.dump(recs, f, indent=2, ensure_ascii=False)
        print("Saved summary to %s" % args.summary)


if __name__ == "__main__":
    main()
