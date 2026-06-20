"""
Search history for weight tuning.

Tracks explored weight candidates to prevent redundant re-exploration.

Usage:
  python tools/search_history.py --list
  python tools/search_history.py --check --parameter P --value V
  python tools/search_history.py --add --parameter P --value V --result R --stage S \
      --anomalies-per-game A --safety S --reason "..."
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "reports", "search_history.json"
)


def load(path: str = _DEFAULT_PATH) -> dict:
    if not os.path.exists(path):
        return {"schema_version": "1.0", "entries": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(data: dict, path: str = _DEFAULT_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_entries(data: dict, parameter: str, value: float = None) -> list:
    entries = []
    for e in data.get("entries", []):
        if e.get("parameter") != parameter:
            continue
        if value is not None and e.get("value") != value:
            continue
        entries.append(e)
    return entries


def is_explored(data: dict, parameter: str, value: float) -> bool:
    return len(find_entries(data, parameter, value)) > 0


def should_skip(data: dict, parameter: str, value: float) -> tuple:
    """Check if a candidate should be skipped based on history.

    Returns (skip: bool, reason: str).
    Rules:
      - rejected candidate: skip unless stable baseline has changed
      - accepted candidate: skip (already adopted)
      - held candidate: do not skip (may re-explore)
    """
    entries = find_entries(data, parameter, value)
    if not entries:
        return False, "not explored"
    latest = entries[-1]
    result = latest.get("result", "")
    if result == "accept":
        return True, f"already accepted ({latest.get('date', '?')})"
    if result == "reject":
        return True, f"rejected ({latest.get('date', '?')}): {latest.get('reason', '')}"
    return False, f"held ({latest.get('date', '?')}), re-exploration allowed"


def add_entry(
    data: dict,
    parameter: str,
    value: float,
    result: str,
    stage: str,
    anomalies_per_game: float = None,
    safety: str = "all_0",
    reason: str = "",
    source_report: str = "",
) -> dict:
    entry = {
        "parameter": parameter,
        "value": value,
        "result": result,
        "stage": stage,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "anomalies_per_game": anomalies_per_game,
        "safety": safety,
        "reason": reason,
    }
    if source_report:
        entry["source_report"] = source_report
    data.setdefault("entries", []).append(entry)
    return entry


def list_entries(data: dict) -> None:
    entries = data.get("entries", [])
    if not entries:
        print("No entries.")
        return
    print(f"{'Parameter':<40s} {'Value':>8s} {'Result':>8s} {'Stage':>6s} "
          f"{'Anom/g':>7s} {'Safety':>7s} {'Date':>12s}")
    print("-" * 95)
    for e in entries:
        apg = e.get("anomalies_per_game")
        apg_s = f"{apg:.2f}" if apg is not None else "-"
        print(f"  {e.get('parameter',''):<38s} {e.get('value',''):>8} "
              f"{e.get('result',''):>8s} {e.get('stage',''):>6s} "
              f"{apg_s:>7s} {e.get('safety',''):>7s} {e.get('date',''):>12s}")


def main():
    parser = argparse.ArgumentParser(description="Weight tuning search history")
    parser.add_argument("--history", default=_DEFAULT_PATH, help="Path to search_history.json")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all entries")
    group.add_argument("--check", action="store_true", help="Check if parameter/value explored")
    group.add_argument("--add", action="store_true", help="Add new entry")

    parser.add_argument("--parameter", help="Weight parameter name")
    parser.add_argument("--value", type=float, help="Weight value")
    parser.add_argument("--result", choices=["accept", "hold", "reject", "baseline"], help="Decision")
    parser.add_argument("--stage", help="Evaluation stage (30g, 50g, 200g)")
    parser.add_argument("--anomalies-per-game", type=float, help="Anomalies per game")
    parser.add_argument("--safety", default="all_0", help="Safety status")
    parser.add_argument("--reason", default="", help="Decision reason")
    parser.add_argument("--source-report", default="", help="Source report path")

    args = parser.parse_args()
    data = load(args.history)

    if args.list:
        list_entries(data)
        return

    if not args.parameter:
        parser.error("--parameter is required for --check and --add")
    if args.value is None:
        parser.error("--value is required for --check and --add")

    if args.check:
        skip, reason = should_skip(data, args.parameter, args.value)
        explored = is_explored(data, args.parameter, args.value)
        print(f"Parameter: {args.parameter}")
        print(f"Value:     {args.value}")
        print(f"Explored:  {explored}")
        print(f"Skip:      {skip}")
        print(f"Reason:    {reason}")
        sys.exit(1 if skip else 0)

    if args.add:
        if not args.result:
            parser.error("--result is required for --add")
        if not args.stage:
            parser.error("--stage is required for --add")
        entry = add_entry(
            data, args.parameter, args.value, args.result, args.stage,
            args.anomalies_per_game, args.safety, args.reason, args.source_report,
        )
        save(data, args.history)
        print(f"Added: {entry['parameter']}={entry['value']} -> {entry['result']} ({entry['stage']})")


if __name__ == "__main__":
    main()
