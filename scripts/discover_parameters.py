"""
Discover hardcoded scoring parameters in agent/ files.

Scans Python files for numeric literals used in scoring decisions
and outputs a report of candidates for externalization.

Usage:
  python scripts/discover_parameters.py
  python scripts/discover_parameters.py --csv experiments/results/parameter_discovery.csv
"""
from __future__ import annotations
import argparse
import ast
import os
import re
import sys
from typing import List, Dict

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_AGENT_DIR = os.path.join(_REPO_ROOT, "agent")

_SCAN_FILES = [
    "policy.py", "ionos_rules.py", "turn_rule_engine.py",
    "damage_predictor.py", "evaluator.py", "planner.py",
    "effect_engine.py", "card_metadata.py", "turn_plan.py",
    "advantage.py", "win_condition.py", "opponent_model.py",
]

_ALREADY_EXTERNALIZED = {
    "advantage_weight", "energy_to_plan_bonus", "energy_to_plan_bonus_no_need",
    "attack_suppress_penalty", "retreat_to_better_attacker_bonus",
    "voltorb_ko_attack_bonus", "voltorb_damage_scaling",
    "energy_attack_enablement_bonus", "evolve_first_bellibolt_bonus",
    "evolve_first_kilowattrel_bonus", "legal_attack_score",
}

_SCORE_PATTERNS = [
    re.compile(r'score\s*[+\-*/]?=\s*(-?\d+\.?\d*)'),
    re.compile(r'return\s+(-?\d+\.?\d*)\s*,'),
    re.compile(r'[+\-]\s*(\d+\.?\d*)\s*$'),
]

_THRESHOLD_PATTERNS = [
    re.compile(r'(?:hp|energy|count|deck_count|prizes|bench)\s*[<>=!]+\s*(\d+\.?\d*)'),
    re.compile(r'(\d+\.?\d*)\s*[<>=!]+\s*(?:hp|energy|count|deck_count|prizes|bench)'),
]

_FIXED_KEYWORDS = {"avoid_end_when_attack", "avoid_retreat_when_attack",
                    "empty_bench", "winning_attack", "deck_out_loss",
                    "resistance_value"}

_DECK_KEYWORDS = {"voltorb", "bellibolt", "kilowattrel", "tadbulb", "wattrel",
                   "iono", "poffin", "lightning"}


def _guess_role(line: str, value: float) -> str:
    low = line.lower()
    if "penalty" in low or value < 0:
        return "penalty"
    if "bonus" in low or "boost" in low:
        return "bonus"
    if any(t in low for t in ("threshold", "<=", ">=", "< ", "> ")):
        return "threshold"
    if "weight" in low or "scale" in low or "factor" in low:
        return "weight"
    if "score" in low:
        return "score"
    return "constant"


def _guess_category(line: str, filepath: str) -> str:
    low = line.lower()
    fname = os.path.basename(filepath).lower()

    for kw in _FIXED_KEYWORDS:
        if kw in low:
            return "fixed_rules"

    if fname == "ionos_rules.py" or any(kw in low for kw in _DECK_KEYWORDS):
        return "deck_params"

    return "global_params"


def scan_file(filepath: str) -> List[Dict]:
    candidates = []
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
            continue

        for pat in _SCORE_PATTERNS + _THRESHOLD_PATTERNS:
            for m in pat.finditer(stripped):
                try:
                    val = float(m.group(1))
                except (ValueError, IndexError):
                    continue

                if abs(val) < 1.0 and "weight" not in stripped.lower() and "scale" not in stripped.lower():
                    continue
                if val in (0, 1, 2):
                    if "score" not in stripped.lower() and "return" not in stripped.lower():
                        continue

                snippet = stripped[:100]
                role = _guess_role(stripped, val)
                cat = _guess_category(stripped, filepath)

                candidates.append({
                    "file": os.path.basename(filepath),
                    "line": i,
                    "value": val,
                    "snippet": snippet,
                    "role": role,
                    "category": cat,
                })

    return candidates


def deduplicate(candidates: List[Dict]) -> List[Dict]:
    seen = set()
    result = []
    for c in candidates:
        key = (c["file"], c["line"], c["value"])
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def format_markdown(candidates: List[Dict]) -> str:
    lines = ["# Parameter Discovery Report", "",
             f"Auto-discovered {len(candidates)} candidate parameters.", ""]

    by_cat = {}
    for c in candidates:
        by_cat.setdefault(c["category"], []).append(c)

    for cat in ["global_params", "deck_params", "fixed_rules", "unknown"]:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"## {cat} ({len(items)})")
        lines.append("")
        lines.append("| File | Line | Value | Role | Snippet |")
        lines.append("|------|------|-------|------|---------|")
        for c in sorted(items, key=lambda x: (x["file"], x["line"])):
            snip = c["snippet"][:60].replace("|", "\\|")
            lines.append(f"| {c['file']} | {c['line']} | {c['value']} | {c['role']} | {snip} |")
        lines.append("")

    return "\n".join(lines)


def format_csv(candidates: List[Dict]) -> str:
    lines = ["file,line,value,role,category,snippet"]
    for c in sorted(candidates, key=lambda x: (x["file"], x["line"])):
        snip = c["snippet"][:80].replace('"', '""')
        lines.append(f'{c["file"]},{c["line"]},{c["value"]},{c["role"]},{c["category"]},"{snip}"')
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Discover hardcoded parameters")
    parser.add_argument("--csv", help="Output CSV path")
    parser.add_argument("--md", default=os.path.join(_REPO_ROOT, "docs", "parameter_discovery_report.md"))
    args = parser.parse_args()

    all_candidates = []
    for fname in _SCAN_FILES:
        fpath = os.path.join(_AGENT_DIR, fname)
        if os.path.exists(fpath):
            all_candidates.extend(scan_file(fpath))

    all_candidates = deduplicate(all_candidates)

    md = format_markdown(all_candidates)
    os.makedirs(os.path.dirname(args.md), exist_ok=True)
    with open(args.md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Markdown: {args.md} ({len(all_candidates)} candidates)")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", encoding="utf-8") as f:
            f.write(format_csv(all_candidates))
        print(f"CSV: {args.csv}")

    by_cat = {}
    for c in all_candidates:
        by_cat.setdefault(c["category"], []).append(c)
    for cat in ["global_params", "deck_params", "fixed_rules"]:
        print(f"  {cat}: {len(by_cat.get(cat, []))}")


if __name__ == "__main__":
    main()
