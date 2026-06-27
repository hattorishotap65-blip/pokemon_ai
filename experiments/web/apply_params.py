"""Apply params recommendations to params.json.

Usage:
    python3 experiments/web/apply_params.py \
        experiments/web/human_traces/params_recommendations.json \
        experiments/agents/raging_bolt/params.json

    python3 experiments/web/apply_params.py \
        experiments/web/human_traces/params_recommendations.json \
        experiments/agents/raging_bolt/params.json \
        --yes  # skip confirmation
"""
import json
import os
import shutil
import sys


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def preview_changes(current, proposed):
    """Return list of (param, old, new, delta) for changed params."""
    changes = []
    for param, new_val in sorted(proposed.items()):
        if param.startswith("_"):
            continue
        old_val = current.get(param)
        if old_val is None:
            changes.append((param, None, new_val, new_val))
        elif old_val != new_val:
            changes.append((param, old_val, new_val, new_val - old_val))
    return changes


def apply_changes(params_path, proposed, backup=True):
    """Apply proposed values to params.json. Creates .bak backup."""
    current = load_json(params_path)

    if backup:
        bak = params_path + ".bak"
        shutil.copy2(params_path, bak)

    for param, new_val in proposed.items():
        if param.startswith("_"):
            continue
        current[param] = new_val

    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return current


def main():
    if len(sys.argv) < 3:
        print("Usage: python apply_params.py <recommendations.json> <params.json> [--yes]")
        sys.exit(1)

    recs_path = sys.argv[1]
    params_path = sys.argv[2]
    auto_yes = "--yes" in sys.argv

    recs = load_json(recs_path)
    proposed = recs.get("proposed", {})

    if not proposed:
        print("No proposed changes.")
        return

    current = load_json(params_path)
    changes = preview_changes(current, proposed)

    if not changes:
        print("No changes to apply (all values already match).")
        return

    summary = recs.get("summary", {})
    print("Based on: %d decisions, %.1f%% agreement" % (
        summary.get("total_decisions", 0),
        summary.get("agreement_pct", 0),
    ))
    print()
    print("Proposed changes (%d params):" % len(changes))
    print("  %-40s  %8s  %8s  %8s" % ("param", "current", "new", "delta"))
    print("  " + "-" * 70)
    for param, old, new, delta in changes:
        old_str = str(old) if old is not None else "(new)"
        sign = "+" if delta > 0 else ""
        print("  %-40s  %8s  %8s  %s%s" % (param, old_str, new, sign, delta))
    print()
    print("Target: %s" % params_path)

    if not auto_yes:
        try:
            ans = input("Apply? [y/N]: ").strip().lower()
        except EOFError:
            ans = "n"
        if ans != "y":
            print("Cancelled.")
            return

    result = apply_changes(params_path, proposed)
    print("Applied %d changes. Backup: %s.bak" % (len(changes), params_path))


if __name__ == "__main__":
    main()
