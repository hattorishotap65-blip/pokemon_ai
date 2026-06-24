"""
Analyze action patterns from game logs.

Compares action distributions, KO capture rates, energy allocation,
and early/late game behavior between agents. Works with self-play
JSONL logs and Kaggle episode JSON.

Usage:
  python experiments/analyze_top_episode_patterns.py \
      --input artifacts/area_fix_only_submission_smoke_50g.jsonl \
      --label own_agent \
      --output artifacts/own_agent_action_patterns.json

  python experiments/analyze_top_episode_patterns.py \
      --from-range 280000 280050 \
      --label own_agent \
      --output artifacts/own_agent_action_patterns.json

  python experiments/analyze_top_episode_patterns.py \
      --input artifacts/top_episode_sample.jsonl \
      --label top_agents \
      --output artifacts/top_episode_patterns.json
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

_AREA_ACTIVE = 4
_AREA_BENCH = 5
_MAIN_ATTACKERS = {"265", "269", "271"}
_IONO_ENERGY_REQ = {"265": 2, "268": 1, "269": 4, "270": 1, "271": 3}

_ACTION_NAMES = {
    0: "NUMBER", 1: "YES", 2: "NO", 3: "CARD", 4: "TOOL_CARD",
    5: "ENERGY_CARD", 6: "ENERGY", 7: "PLAY", 8: "ATTACH",
    9: "EVOLVE", 10: "ABILITY", 11: "DISCARD", 12: "RETREAT",
    13: "ATTACK", 14: "END", 15: "SKILL", 16: "SPECIAL_CONDITION",
}


def load_entries(path: str) -> List[dict]:
    entries = []
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            entries = data.get("steps") or [data]
    return entries


def _phase(turn: int) -> str:
    if turn <= 3:
        return "early"
    if turn <= 8:
        return "mid"
    return "late"


def analyze_game(entries: List[dict]) -> dict:
    """Analyze one game's entries and return per-decision stats."""
    stats = {
        "decisions": 0,
        "by_phase": {"early": defaultdict(int), "mid": defaultdict(int), "late": defaultdict(int)},
        "selected_type": defaultdict(int),
        "attack_when_legal": 0,
        "attack_legal_total": 0,
        "ko_when_possible": 0,
        "ko_possible_total": 0,
        "end_when_legal_attack": 0,
        "attach_to_active": 0,
        "attach_to_bench": 0,
        "attach_to_attacker": 0,
        "attach_to_non_attacker": 0,
        "attach_total": 0,
        "active_energy_starved": 0,
        "bench_oversetup": 0,
        "zero_damage_attack": 0,
        "completed_attacker_no_attack": 0,
        "turns": 0,
    }

    max_turn = 0
    has_attacked = False
    bellibolt_done = False
    kilowattrel_done = False

    for entry in entries:
        candidates = entry.get("top_candidates") or []
        if not candidates:
            continue

        ss = entry.get("state_summary") or {}
        turn = ss.get("turn", entry.get("game_turn", 0)) or 0
        max_turn = max(max_turn, turn)
        phase = _phase(turn)

        stats["decisions"] += 1

        selected = None
        for c in candidates:
            if c.get("selected"):
                selected = c
                break
        if not selected:
            selected = candidates[0] if candidates else {}

        opt_type = selected.get("option_type", 0)
        type_name = _ACTION_NAMES.get(opt_type, str(opt_type))
        stats["selected_type"][type_name] = stats["selected_type"].get(type_name, 0) + 1
        stats["by_phase"][phase][type_name] = stats["by_phase"][phase].get(type_name, 0) + 1

        has_legal_attack = any(
            c.get("is_attack") or c.get("option_type") == 13
            for c in candidates
        )
        has_ko = any(
            (c.get("is_attack") or c.get("option_type") == 13)
            and "ko" in str(c.get("reason") or c.get("rule_reason") or "").lower()
            for c in candidates
        )
        is_attack = selected.get("is_attack") or opt_type == 13
        is_end = selected.get("is_end") or opt_type == 14

        if has_legal_attack:
            stats["attack_legal_total"] += 1
            if is_attack:
                stats["attack_when_legal"] += 1
                has_attacked = True

        if has_ko:
            stats["ko_possible_total"] += 1
            if is_attack:
                stats["ko_when_possible"] += 1

        if is_end and has_legal_attack:
            stats["end_when_legal_attack"] += 1

        if opt_type == 8:
            stats["attach_total"] += 1
            area = selected.get("inPlayArea")
            if area == _AREA_ACTIVE:
                stats["attach_to_active"] += 1
                target_cid = str(ss.get("active_card_id", ""))
                if target_cid in _MAIN_ATTACKERS:
                    stats["attach_to_attacker"] += 1
                else:
                    stats["attach_to_non_attacker"] += 1
            elif area == _AREA_BENCH:
                stats["attach_to_bench"] += 1
                stats["attach_to_non_attacker"] += 1

            active_cid = str(ss.get("active_card_id", ""))
            active_energy = ss.get("active_energy", 0) or 0
            req = _IONO_ENERGY_REQ.get(active_cid, 0)
            if area == _AREA_BENCH and req > 0 and active_energy < req:
                stats["active_energy_starved"] += 1

            if (area == _AREA_BENCH
                    and stats["attach_to_bench"] >= 3
                    and stats["attach_to_active"] <= 1):
                stats["bench_oversetup"] += 1

        if opt_type == 9:
            resolved = str(selected.get("resolved_card_id") or "")
            if resolved == "269":
                bellibolt_done = True
            elif resolved == "271":
                kilowattrel_done = True

        if is_attack:
            reason = str(selected.get("reason") or selected.get("rule_reason") or "")
            if "zero_damage" in reason.lower() or "0_damage" in reason.lower():
                stats["zero_damage_attack"] += 1

    stats["turns"] = max_turn
    if (bellibolt_done or kilowattrel_done) and not has_attacked:
        stats["completed_attacker_no_attack"] = 1

    return stats


def aggregate(all_stats: List[dict]) -> dict:
    """Aggregate per-game stats into summary."""
    n = len(all_stats)
    if n == 0:
        return {}

    totals = defaultdict(int)
    type_totals = defaultdict(int)
    phase_totals = {"early": defaultdict(int), "mid": defaultdict(int), "late": defaultdict(int)}

    for s in all_stats:
        for k in ["decisions", "attack_when_legal", "attack_legal_total",
                   "ko_when_possible", "ko_possible_total",
                   "end_when_legal_attack", "attach_to_active", "attach_to_bench",
                   "attach_to_attacker", "attach_to_non_attacker", "attach_total",
                   "active_energy_starved", "bench_oversetup",
                   "zero_damage_attack", "completed_attacker_no_attack", "turns"]:
            totals[k] += s.get(k, 0)
        for t, c in s.get("selected_type", {}).items():
            type_totals[t] += c
        for phase in ["early", "mid", "late"]:
            for t, c in s.get("by_phase", {}).get(phase, {}).items():
                phase_totals[phase][t] += c

    d = totals["decisions"] or 1
    atk_legal = totals["attack_legal_total"] or 1
    ko_total = totals["ko_possible_total"] or 1
    att_total = totals["attach_total"] or 1

    return {
        "games": n,
        "total_decisions": totals["decisions"],
        "total_turns": totals["turns"],
        "avg_turns": round(totals["turns"] / n, 1),
        "action_distribution": dict(sorted(type_totals.items())),
        "action_pct": {
            k: round(v / d * 100, 2) for k, v in sorted(type_totals.items())
        },
        "phase_distribution": {
            p: dict(sorted(phase_totals[p].items())) for p in ["early", "mid", "late"]
        },
        "attack_when_legal": totals["attack_when_legal"],
        "attack_legal_total": totals["attack_legal_total"],
        "attack_when_legal_rate": round(totals["attack_when_legal"] / atk_legal, 4),
        "ko_when_possible": totals["ko_when_possible"],
        "ko_possible_total": totals["ko_possible_total"],
        "ko_capture_rate": round(totals["ko_when_possible"] / ko_total, 4),
        "miss_ko": totals["ko_possible_total"] - totals["ko_when_possible"],
        "end_when_legal_attack": totals["end_when_legal_attack"],
        "end_when_legal_attack_rate": round(totals["end_when_legal_attack"] / atk_legal, 4),
        "attach_to_active": totals["attach_to_active"],
        "attach_to_bench": totals["attach_to_bench"],
        "attach_active_rate": round(totals["attach_to_active"] / att_total, 4),
        "attach_to_attacker": totals["attach_to_attacker"],
        "attach_to_non_attacker": totals["attach_to_non_attacker"],
        "active_energy_starved": totals["active_energy_starved"],
        "bench_oversetup": totals["bench_oversetup"],
        "zero_damage_attack": totals["zero_damage_attack"],
        "completed_attacker_no_attack": totals["completed_attacker_no_attack"],
    }


def _convert_feature_rows(rows: List[dict]) -> Dict[int, List[dict]]:
    """Convert flat feature rows (from action_feature_logging) into
    per-game lists of pseudo log entries with top_candidates."""
    by_game: Dict[int, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        gid = r.get("game_id", 0)
        did = r.get("decision_id", "")
        by_game[gid][did].append(r)

    result: Dict[int, List[dict]] = {}
    for gid, decisions in by_game.items():
        entries = []
        for did, cands in sorted(decisions.items()):
            first = cands[0] if cands else {}
            entry = {
                "game_id": gid,
                "game_turn": first.get("turn", 0),
                "state_summary": {
                    "turn": first.get("turn", 0),
                    "active_card_id": first.get("active_card_id", ""),
                    "active_hp": first.get("active_hp", 0),
                    "active_energy": first.get("active_energy", 0),
                    "opp_active_card_id": first.get("opponent_active_card_id", ""),
                    "opp_active_hp": first.get("opponent_active_hp", 0),
                    "prizes_remaining": first.get("prize_remaining", 6),
                    "opp_prizes": first.get("opponent_prize_remaining", 6),
                    "bench_count": first.get("bench_size", 0),
                    "deck_count": first.get("deck_count", 0),
                    "hand_count": first.get("hand_count", 0),
                },
                "top_candidates": [
                    {
                        "option_type": c.get("action_type"),
                        "selected": c.get("selected", False),
                        "is_attack": c.get("is_attack", False),
                        "is_end": c.get("is_end", False),
                        "inPlayArea": _AREA_ACTIVE if c.get("attach_to_active") else (
                            _AREA_BENCH if c.get("attach_to_bench") else None
                        ),
                        "resolved_card_id": c.get("evolve_to_card_id", ""),
                        "reason": c.get("rule_reason", ""),
                        "rule_reason": c.get("rule_reason", ""),
                        "can_ko": c.get("can_ko", False),
                        "is_zero_damage_attack": c.get("is_zero_damage_attack", False),
                    }
                    for c in cands
                ],
            }
            entries.append(entry)
        result[gid] = entries
    return result


def format_markdown(label: str, agg: dict) -> str:
    lines = [f"### {label} ({agg['games']} games, {agg['total_decisions']} decisions)"]
    lines.append("")

    lines.append("#### Action Distribution")
    lines.append("")
    lines.append("| Action | Count | % |")
    lines.append("|--------|-------|---|")
    for k, v in sorted(agg.get("action_pct", {}).items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {agg['action_distribution'].get(k, 0)} | {v}% |")

    lines.append("")
    lines.append("#### Key Rates")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Attack when legal | {agg['attack_when_legal']}/{agg['attack_legal_total']} ({agg['attack_when_legal_rate']:.1%}) |")
    lines.append(f"| KO capture rate | {agg['ko_when_possible']}/{agg['ko_possible_total']} ({agg['ko_capture_rate']:.1%}) |")
    lines.append(f"| miss_KO | {agg['miss_ko']} |")
    lines.append(f"| END when legal attack | {agg['end_when_legal_attack']} ({agg['end_when_legal_attack_rate']:.1%}) |")
    lines.append(f"| Attach to active | {agg['attach_to_active']}/{agg['attach_to_active'] + agg['attach_to_bench']} ({agg['attach_active_rate']:.1%}) |")
    lines.append(f"| Active energy starved | {agg['active_energy_starved']} |")
    lines.append(f"| Bench oversetup | {agg['bench_oversetup']} |")
    lines.append(f"| zero_damage attack | {agg['zero_damage_attack']} |")
    lines.append(f"| Completed attacker unused | {agg['completed_attacker_no_attack']} |")

    lines.append("")
    lines.append("#### Phase Distribution (early/mid/late)")
    lines.append("")
    all_types = set()
    for p in ["early", "mid", "late"]:
        all_types.update(agg.get("phase_distribution", {}).get(p, {}).keys())
    key_types = ["ATTACK", "ATTACH", "END", "PLAY", "EVOLVE", "RETREAT", "ABILITY"]
    header = "| Phase | " + " | ".join(key_types) + " |"
    sep = "|-------|" + "|".join(["-----"] * len(key_types)) + "|"
    lines.append(header)
    lines.append(sep)
    for p in ["early", "mid", "late"]:
        pd = agg.get("phase_distribution", {}).get(p, {})
        vals = " | ".join(str(pd.get(t, 0)) for t in key_types)
        lines.append(f"| {p} | {vals} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze action patterns from game logs"
    )
    parser.add_argument("--input", nargs="*", default=[],
                        help="Log file paths (JSONL or JSON)")
    parser.add_argument("--from-range", nargs=2, type=int, metavar=("START", "END"),
                        help="Self-play log range")
    parser.add_argument("--label", default="agent",
                        help="Label for this dataset")
    parser.add_argument("--output", default="artifacts/action_patterns.json")
    args = parser.parse_args()

    input_files: List[str] = []
    for pattern in (args.input or []):
        expanded = glob.glob(pattern)
        if expanded:
            input_files.extend(expanded)
        elif os.path.exists(pattern):
            input_files.append(pattern)

    if args.from_range:
        start, end = args.from_range
        for gid in range(start, end):
            path = os.path.join(_REPO_ROOT, "logs", "game_g%05d.jsonl" % gid)
            if os.path.exists(path):
                input_files.append(path)

    if not input_files:
        print("ERROR: no input files")
        parser.print_help()
        sys.exit(1)

    print(f"Analyzing {len(input_files)} files (label: {args.label})...")

    all_stats = []
    for path in input_files:
        entries = load_entries(path)
        if not entries:
            continue

        first = entries[0] if entries else {}
        if "decision_id" in first and "action_type" in first:
            converted = _convert_feature_rows(entries)
            for gid, game_entries in converted.items():
                s = analyze_game(game_entries)
                all_stats.append(s)
        elif "top_candidates" in first:
            s = analyze_game(entries)
            all_stats.append(s)
        else:
            games: Dict[int, List[dict]] = defaultdict(list)
            for e in entries:
                gid = e.get("game_id", 0)
                games[gid].append(e)
            for gid, game_entries in games.items():
                if game_entries and "top_candidates" in game_entries[0]:
                    s = analyze_game(game_entries)
                elif game_entries and "decision_id" in game_entries[0]:
                    conv = _convert_feature_rows(game_entries)
                    for _, ge in conv.items():
                        s = analyze_game(ge)
                        all_stats.append(s)
                    continue
                else:
                    s = analyze_game(game_entries)
                all_stats.append(s)

    agg = aggregate(all_stats)
    agg["label"] = args.label

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {args.output}")
    print(f"\n{format_markdown(args.label, agg)}")


if __name__ == "__main__":
    main()
