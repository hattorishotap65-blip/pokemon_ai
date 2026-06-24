"""
Analyze loss patterns from game logs.

Diagnoses early attack failures, energy allocation issues,
and setup-without-conversion patterns.

Supports two input formats:
  1. Self-play JSONL (logs/game_gNNNNN.jsonl)
  2. Kaggle match log JSON (episode replay)

Usage:
  python experiments/analyze_loss_patterns.py \
      --inputs logs/game_g261000.jsonl logs/game_g261001.jsonl \
      --summary artifacts/early_attack_loss_summary.json

  python experiments/analyze_loss_patterns.py \
      --inputs artifacts/loss_logs/*.json \
      --summary artifacts/early_attack_loss_summary.json

  python experiments/analyze_loss_patterns.py \
      --from-range 261000 261005 \
      --summary artifacts/early_attack_loss_summary.json
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from typing import Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

_IONO_ENERGY_REQ = {"265": 2, "268": 1, "269": 4, "270": 1, "271": 3}
_MAIN_ATTACKERS = {"265", "269", "271"}
_EVOLUTION_TARGETS = {
    "268": "269",  # Tadbulb -> Bellibolt ex
    "270": "271",  # Wattrel -> Kilowattrel
}
_AREA_ACTIVE = 4
_AREA_BENCH = 5


def _energy_needed(card_id: str, current_energy: int) -> int:
    req = _IONO_ENERGY_REQ.get(str(card_id), 0)
    return max(0, req - current_energy) if req > 0 else 0


def load_selfplay_jsonl(path: str) -> List[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def load_kaggle_json(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        steps = data.get("steps") or []
        if steps:
            return steps
        return [data]
    return []


def load_entries(path: str) -> List[dict]:
    if path.endswith(".jsonl"):
        return load_selfplay_jsonl(path)
    return load_kaggle_json(path)


def analyze_one_game(entries: List[dict], source: str) -> dict:
    """Analyze a single game's entries for loss patterns."""
    game_id = ""
    our_attack_count = 0
    opponent_attack_count = 0
    first_attack_turn = None
    total_attach_count = 0
    active_attach_count = 0
    bench_attach_count = 0
    evolve_count = 0
    bench_setup_count = 0
    total_decisions = 0
    max_turn = 0
    first_active = ""
    bellibolt_completed = 0
    kilowattrel_completed = 0
    total_damage_dealt = 0
    total_damage_taken = 0
    opp_first_attack_turn = None
    total_steps = len(entries)

    last_ss: Dict = {}
    last_result = "unknown"

    for entry in entries:
        game_id = game_id or str(entry.get("game_id", ""))
        ss = entry.get("state_summary") or {}
        if ss:
            last_ss = ss
        turn = ss.get("turn", entry.get("game_turn", 0)) or 0
        max_turn = max(max_turn, turn)

        if not first_active and ss.get("active_card_id"):
            first_active = str(ss["active_card_id"])

        r = entry.get("result")
        if r in ("win", "loss"):
            last_result = r

        candidates = entry.get("top_candidates") or []
        if not candidates:
            continue

        total_decisions += 1

        selected = None
        for c in candidates:
            if c.get("selected"):
                selected = c
                break
        if not selected:
            selected = candidates[0] if candidates else {}

        opt_type = selected.get("option_type")

        if selected.get("is_attack") or opt_type == 13:
            our_attack_count += 1
            if first_attack_turn is None:
                first_attack_turn = turn
            reason = str(selected.get("reason") or selected.get("rule_reason") or "")
            if "ko" in reason.lower():
                opp_hp = ss.get("opp_active_hp", 0) or 0
                total_damage_dealt += opp_hp
            else:
                total_damage_dealt += 20

        if opt_type == 8:
            total_attach_count += 1
            in_play_area = selected.get("inPlayArea")
            if in_play_area == _AREA_ACTIVE:
                active_attach_count += 1
            elif in_play_area == _AREA_BENCH:
                bench_attach_count += 1

        if opt_type == 9:
            evolve_count += 1
            resolved = str(selected.get("resolved_card_id") or "")
            if resolved == "269":
                bellibolt_completed += 1
            elif resolved == "271":
                kilowattrel_completed += 1

        if opt_type == 7:
            bench_setup_count += 1

    prizes = last_ss.get("prizes_remaining", 6)
    opp_prizes = last_ss.get("opp_prizes", 6)
    if last_result == "unknown":
        if prizes == 0:
            last_result = "win"
        elif opp_prizes == 0:
            last_result = "loss"

    bench_attach_ratio = (
        round(bench_attach_count / total_attach_count, 3)
        if total_attach_count > 0 else 0.0
    )
    attack_zero = our_attack_count == 0
    active_energy_lag = (
        active_attach_count == 0 and bench_attach_count >= 2
    )
    bench_over_setup = (
        bench_attach_count >= 3 and active_attach_count <= 1
        and our_attack_count <= 2
    )
    completed_no_attack = (
        (bellibolt_completed > 0 or kilowattrel_completed > 0)
        and our_attack_count == 0
    )
    low_damage = our_attack_count > 0 and our_attack_count <= 2
    turns_until_first = (
        first_attack_turn if first_attack_turn is not None else max_turn
    )
    early_attack_missing = turns_until_first >= 5 and our_attack_count <= 2
    opponent_outpaced = opp_prizes < prizes and last_result != "win"

    return {
        "source": source,
        "game_id": game_id,
        "result": last_result,
        "turns": max_turn,
        "steps": total_steps,
        "decisions": total_decisions,
        "prizes_remaining": prizes,
        "opp_prizes_remaining": opp_prizes,
        "our_attack_count": our_attack_count,
        "opponent_attack_count": opponent_attack_count,
        "first_attack_turn": first_attack_turn,
        "turns_until_first_attack": turns_until_first,
        "attack_zero_game": attack_zero,
        "total_damage_dealt": total_damage_dealt,
        "total_attach_count": total_attach_count,
        "active_attach_count": active_attach_count,
        "bench_attach_count": bench_attach_count,
        "bench_attach_ratio": bench_attach_ratio,
        "active_energy_lag": active_energy_lag,
        "bench_over_setup": bench_over_setup,
        "first_active_pokemon": first_active,
        "bench_setup_count": bench_setup_count,
        "evolve_count": evolve_count,
        "bellibolt_ex_completed": bellibolt_completed,
        "kilowattrel_completed": kilowattrel_completed,
        "completed_attacker_no_attack": completed_no_attack,
        "patterns": {
            "early_attack_missing": early_attack_missing,
            "attack_zero_loss": attack_zero and last_result == "loss",
            "bench_over_setup": bench_over_setup,
            "active_energy_lag": active_energy_lag,
            "completed_attacker_no_attack": completed_no_attack,
            "low_damage_output": low_damage,
            "opponent_outpaced_us": opponent_outpaced,
        },
    }


def format_markdown(results: List[dict]) -> str:
    lines = []

    lines.append("## Per Match Table")
    lines.append("")
    lines.append(
        "| Game | Result | Attacks | 1st Atk Turn | "
        "Active Attach | Bench Attach | 1st Active | Key Pattern |"
    )
    lines.append(
        "|------|--------|---------|--------------|"
        "---------------|--------------|------------|-------------|"
    )
    for r in results:
        patterns = r.get("patterns") or {}
        active_patterns = [k for k, v in patterns.items() if v]
        key_pattern = ", ".join(active_patterns[:2]) if active_patterns else "none"
        first_atk = (
            str(r["first_attack_turn"]) if r["first_attack_turn"] is not None
            else "never"
        )
        lines.append(
            f"| {r['game_id']} | {r['result']} | {r['our_attack_count']} "
            f"| {first_atk} | {r['active_attach_count']} "
            f"| {r['bench_attach_count']} | {r['first_active_pokemon']} "
            f"| {key_pattern} |"
        )

    lines.append("")
    lines.append("## Pattern Frequency")
    lines.append("")
    pattern_counts: Dict[str, int] = {}
    for r in results:
        for k, v in (r.get("patterns") or {}).items():
            if v:
                pattern_counts[k] = pattern_counts.get(k, 0) + 1
    lines.append("| Pattern | Count | Rate |")
    lines.append("|---------|-------|------|")
    total = len(results) or 1
    for k in sorted(pattern_counts.keys(), key=lambda x: -pattern_counts[x]):
        lines.append(
            f"| {k} | {pattern_counts[k]} | "
            f"{pattern_counts[k]/total:.0%} |"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze loss patterns from game logs"
    )
    parser.add_argument(
        "--inputs", nargs="*", default=[],
        help="Log file paths (JSONL or JSON). Supports glob patterns."
    )
    parser.add_argument(
        "--from-range", nargs=2, type=int, metavar=("START", "END"),
        help="Analyze self-play logs from START to END game IDs"
    )
    parser.add_argument(
        "--losses-only", action="store_true",
        help="Only include games detected as losses"
    )
    parser.add_argument(
        "--summary", default="artifacts/early_attack_loss_summary.json",
        help="Output summary JSON path"
    )
    args = parser.parse_args()

    input_files: List[str] = []
    for pattern in (args.inputs or []):
        expanded = glob.glob(pattern)
        if expanded:
            input_files.extend(expanded)
        elif os.path.exists(pattern):
            input_files.append(pattern)
        else:
            print(f"WARNING: {pattern} not found, skipping")

    if args.from_range:
        start, end = args.from_range
        for gid in range(start, end):
            path = os.path.join(_REPO_ROOT, "logs", "game_g%05d.jsonl" % gid)
            if os.path.exists(path):
                input_files.append(path)

    if not input_files:
        print("ERROR: no input files found")
        parser.print_help()
        sys.exit(1)

    print(f"Analyzing {len(input_files)} game logs...")
    results = []
    for path in input_files:
        entries = load_entries(path)
        if not entries:
            print(f"  WARNING: {path} has no entries, skipping")
            continue
        r = analyze_one_game(entries, os.path.basename(path))
        if args.losses_only and r["result"] != "loss":
            continue
        results.append(r)

    print(f"  Analyzed: {len(results)} games")

    pattern_counts: Dict[str, int] = {}
    for r in results:
        for k, v in (r.get("patterns") or {}).items():
            if v:
                pattern_counts[k] = pattern_counts.get(k, 0) + 1

    summary = {
        "total_games": len(results),
        "pattern_counts": pattern_counts,
        "per_game": results,
    }

    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSaved summary to {args.summary}")

    print("\n" + format_markdown(results))

    if pattern_counts:
        print("\n## Summary")
        total = len(results) or 1
        for k in sorted(pattern_counts.keys(), key=lambda x: -pattern_counts[x]):
            print(f"  {k}: {pattern_counts[k]}/{total}")


if __name__ == "__main__":
    main()
