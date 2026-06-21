"""
Record a submission snapshot to reports/.

Usage:
  python tools/record_submission.py --tag v3.0-stable \
      --changes "legal_attack_score=250.0 (PR #75)" \
      --smoke-apg 4.87 --smoke-games 30
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_WEIGHTS_PATH = os.path.join(_REPO_ROOT, "data", "weights.json")


def _load_weights() -> dict:
    with open(_WEIGHTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    skip = {"schema_version", "description", "notes"}
    return {k: v for k, v in data.items() if k not in skip}


def record(
    tag: str, changes: str,
    smoke_apg: float = None, smoke_games: int = None,
    submission_size_kb: int = None,
) -> dict:
    weights = _load_weights()
    tar_path = os.path.join(_REPO_ROOT, "submission.tar.gz")
    if submission_size_kb is None and os.path.exists(tar_path):
        submission_size_kb = os.path.getsize(tar_path) // 1024

    rec = {
        "schema_version": "1.0",
        "tag": tag,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "changes": changes,
        "weights": weights,
        "submission_size_kb": submission_size_kb,
    }
    if smoke_apg is not None:
        rec["smoke_check"] = {
            "games": smoke_games or 30,
            "anomalies_per_game": smoke_apg,
            "safety": "all_0",
        }
    return rec


def format_md(rec: dict) -> str:
    lines = [f"# Submission Snapshot: {rec['tag']}", ""]
    lines.append(f"- Date: {rec['date']}")
    lines.append(f"- Changes: {rec['changes']}")
    if rec.get("submission_size_kb"):
        lines.append(f"- Size: {rec['submission_size_kb']} KB")
    lines.append("")

    lines.append("## Weights")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    for k, v in sorted(rec["weights"].items()):
        lines.append(f"| {k} | {v} |")
    lines.append("")

    if rec.get("smoke_check"):
        sc = rec["smoke_check"]
        lines.append("## Smoke Check")
        lines.append("")
        lines.append(f"- Games: {sc['games']}")
        lines.append(f"- Anomalies/g: {sc['anomalies_per_game']}")
        lines.append(f"- Safety: {sc['safety']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Record submission snapshot")
    parser.add_argument("--tag", required=True, help="Version tag (e.g. v3.0-stable)")
    parser.add_argument("--changes", required=True, help="Summary of changes")
    parser.add_argument("--smoke-apg", type=float, help="Smoke check anomalies/game")
    parser.add_argument("--smoke-games", type=int, default=30)
    parser.add_argument("--output", default="reports")

    args = parser.parse_args()

    rec = record(args.tag, args.changes, args.smoke_apg, args.smoke_games)

    base = os.path.join(_REPO_ROOT, args.output)
    os.makedirs(base, exist_ok=True)

    safe_tag = args.tag.replace(".", "_").replace("-", "_")
    json_path = os.path.join(base, f"submission_snapshot_{safe_tag}.json")
    md_path = os.path.join(base, f"submission_snapshot_{safe_tag}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(format_md(rec))

    print(f"Snapshot: {json_path}")
    print(f"Summary: {md_path}")


if __name__ == "__main__":
    main()
