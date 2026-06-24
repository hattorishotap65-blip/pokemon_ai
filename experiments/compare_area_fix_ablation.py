"""
Compare area fix ablation results from self-play logs.

Wraps compare_ml_hybrid_bonus.py aggregation for A/B/C ablation.

Usage:
  python experiments/compare_area_fix_ablation.py \
      --inputs \
        A_baseline=artifacts/area_fix_ablation_baseline_100g.jsonl \
        B_fix_only=artifacts/area_fix_ablation_fix_only_100g.jsonl \
        C_fix_comp=artifacts/area_fix_ablation_attack_comp_100g.jsonl \
      --summary artifacts/area_fix_ablation_summary.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

from experiments.compare_ml_hybrid_bonus import (
    load_jsonl, aggregate_one, format_markdown_tables,
)


def main():
    parser = argparse.ArgumentParser(
        description="Compare area fix ablation results"
    )
    parser.add_argument(
        "--inputs", nargs="+", required=True,
        help="label=path pairs, e.g. A_baseline=artifacts/baseline.jsonl"
    )
    parser.add_argument(
        "--summary", default="artifacts/area_fix_ablation_summary.json",
    )
    args = parser.parse_args()

    all_results = []
    for inp in args.inputs:
        if "=" in inp:
            label, path = inp.split("=", 1)
        else:
            label = os.path.splitext(os.path.basename(inp))[0]
            path = inp

        print(f"Loading {label} from {path}...")
        data = load_jsonl(path)
        print(f"  {len(data)} rows")

        result = aggregate_one(label, data)
        all_results.append(result)

        ko_cands = 0
        ko_selected = 0
        from collections import defaultdict
        games = defaultdict(list)
        for row in data:
            games[row.get("game_id", 0)].append(row)
        for gid, rows in games.items():
            decision_groups = defaultdict(list)
            for r in rows:
                did = r.get("decision_id", "")
                if did:
                    decision_groups[did].append(r)
            for did, cands in decision_groups.items():
                has_ko = any(c.get("can_ko") for c in cands)
                if has_ko:
                    ko_cands += 1
                    selected = [c for c in cands if c.get("selected")]
                    if selected and selected[0].get("is_attack"):
                        ko_selected += 1
        result["ko_candidates"] = ko_cands
        result["ko_selected"] = ko_selected
        result["ko_capture_rate"] = (
            round(ko_selected / ko_cands, 4) if ko_cands > 0 else 0.0
        )

        print(f"  Games: {result['games']}, Errors: {result['errors']}, "
              f"miss_KO: {result['miss_ko']}, "
              f"KO capture: {ko_selected}/{ko_cands} "
              f"({result['ko_capture_rate']:.1%})")

    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {args.summary}")

    print("\n" + format_markdown_tables(all_results))

    print("\n### KO Capture Rate")
    print("")
    print("| Config | KO Candidates | KO Selected | Capture Rate | miss_KO |")
    print("|--------|---------------|-------------|--------------|---------|")
    for r in all_results:
        print(
            f"| {r['label']} | {r.get('ko_candidates', 'N/A')} "
            f"| {r.get('ko_selected', 'N/A')} "
            f"| {r.get('ko_capture_rate', 0):.1%} "
            f"| {r['miss_ko']} |"
        )


if __name__ == "__main__":
    main()
