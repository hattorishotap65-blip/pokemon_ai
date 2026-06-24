"""
Compare ML hybrid bonus ratios from self-play logs.

Aggregates per-bonus JSONL outputs from action_feature_logging.py
and produces a summary JSON + markdown table.

Usage:
  python experiments/compare_ml_hybrid_bonus.py \
      --inputs bonus8=artifacts/ml_hybrid_bonus8_100g.jsonl \
               bonus10=artifacts/ml_hybrid_bonus10_100g.jsonl \
               bonus12=artifacts/ml_hybrid_bonus12_100g.jsonl \
               bonus15=artifacts/ml_hybrid_bonus15_100g.jsonl \
      --summary artifacts/ml_hybrid_bonus_sweep_summary.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

_ACTION_TYPE_NAMES = {
    "0": "NUMBER", "1": "YES", "2": "NO", "3": "CARD", "4": "TOOL_CARD",
    "5": "ENERGY_CARD", "6": "ENERGY", "7": "PLAY", "8": "ATTACH",
    "9": "EVOLVE", "10": "ABILITY", "11": "DISCARD", "12": "RETREAT",
    "13": "ATTACK", "14": "END", "15": "SKILL", "16": "SPECIAL_CONDITION",
}


def load_jsonl(path: str) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def aggregate_one(label: str, data: List[dict]) -> dict:
    """Aggregate stats for one bonus ratio run."""
    games: Dict[int, List[dict]] = defaultdict(list)
    for row in data:
        gid = row.get("game_id", 0)
        games[gid].append(row)

    total_games = len(games)
    wins = losses = errors = timeouts = unknown = 0

    selected_types: Dict[str, int] = defaultdict(int)
    total_decisions = 0
    total_candidates = 0
    end_legal_attack = 0
    zero_damage = 0
    miss_ko = 0

    for gid, rows in games.items():
        result = rows[0].get("game_result", "unknown") if rows else "unknown"
        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        elif result == "error":
            errors += 1
        elif result == "timeout":
            timeouts += 1
        else:
            unknown += 1

        decision_groups: Dict[str, List[dict]] = defaultdict(list)
        for r in rows:
            did = r.get("decision_id", "")
            if did:
                decision_groups[did].append(r)

        for did, cands in decision_groups.items():
            total_decisions += 1
            total_candidates += len(cands)

            selected = [c for c in cands if c.get("selected")]
            if selected:
                sel = selected[0]
                t = str(sel.get("action_type", ""))
                selected_types[t] = selected_types.get(t, 0) + 1

                has_legal_attack = any(c.get("has_legal_attack") for c in cands)
                has_ko = any(c.get("can_ko") for c in cands)

                if sel.get("is_end") and has_legal_attack:
                    end_legal_attack += 1
                if sel.get("is_zero_damage_attack"):
                    zero_damage += 1
                if has_ko and not sel.get("is_attack"):
                    miss_ko += 1

    attack_count = selected_types.get("13", 0)
    attach_count = selected_types.get("8", 0)
    end_count = selected_types.get("14", 0)
    retreat_count = selected_types.get("12", 0)

    type_dist = {}
    for k, v in sorted(selected_types.items()):
        name = _ACTION_TYPE_NAMES.get(k, k)
        type_dist[name] = v

    return {
        "label": label,
        "games": total_games,
        "wins": wins,
        "losses": losses,
        "errors": errors,
        "timeouts": timeouts,
        "unknown": unknown,
        "win_rate": round(wins / (wins + losses), 4) if (wins + losses) else 0.0,
        "decisions": total_decisions,
        "candidates": total_candidates,
        "avg_selections": round(total_candidates / total_decisions, 2) if total_decisions else 0.0,
        "end_legal_attack": end_legal_attack,
        "zero_damage": zero_damage,
        "miss_ko": miss_ko,
        "attack_count": attack_count,
        "attach_count": attach_count,
        "end_count": end_count,
        "retreat_count": retreat_count,
        "action_type_distribution": type_dist,
        "notes": "",
    }


def format_markdown_tables(results: List[dict]) -> str:
    lines = []

    lines.append("### Self-Play Results")
    lines.append("")
    lines.append("| Bonus | Games | Wins | Losses | Win Rate | Errors | Timeouts |")
    lines.append("|-------|-------|------|--------|----------|--------|----------|")
    for r in results:
        lines.append(
            f"| {r['label']} | {r['games']} | {r['wins']} | {r['losses']} "
            f"| {r['win_rate']:.1%} | {r['errors']} | {r['timeouts']} |"
        )

    lines.append("")
    lines.append("### Safety Metrics")
    lines.append("")
    lines.append("| Bonus | End+legal_attack | zero_damage | miss_KO |")
    lines.append("|-------|------------------|-------------|---------|")
    for r in results:
        lines.append(
            f"| {r['label']} | {r['end_legal_attack']} | {r['zero_damage']} "
            f"| {r['miss_ko']} |"
        )

    lines.append("")
    lines.append("### Action Type Distribution (selected actions)")
    lines.append("")
    lines.append("| Bonus | ATTACK | ATTACH | END | RETREAT | Decisions |")
    lines.append("|-------|--------|--------|-----|---------|-----------|")
    for r in results:
        lines.append(
            f"| {r['label']} | {r['attack_count']} | {r['attach_count']} "
            f"| {r['end_count']} | {r['retreat_count']} | {r['decisions']} |"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Compare ML hybrid bonus ratios from self-play logs"
    )
    parser.add_argument(
        "--inputs", nargs="+", required=True,
        help="label=path pairs, e.g. bonus8=artifacts/bonus8.jsonl"
    )
    parser.add_argument(
        "--summary", default="artifacts/ml_hybrid_bonus_sweep_summary.json",
        help="Output summary JSON path"
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

        print(f"  Games: {result['games']}, Wins: {result['wins']}, "
              f"Losses: {result['losses']}, Errors: {result['errors']}")

    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved summary to {args.summary}")

    print("\n" + format_markdown_tables(all_results))


if __name__ == "__main__":
    main()
