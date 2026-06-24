"""
Compare candidate agent vs cached Top Episode features.

No self-play needed — reads existing JSONL files only.
Produces a markdown comparison report.

Usage:
  python experiments/compare_candidate_vs_top_cached.py \
      --top-features artifacts/top_episodes_features_cached.jsonl \
      --our-features artifacts/attack_plan_ionos_active_candidate_default_100g.jsonl \
      --our-logs-range 309000 309100 \
      --label "#164 attack plan candidate" \
      --output docs/experiments/top_comparison_attack_plan_candidate_001.md
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional

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


def load_cached_features(path: str) -> List[dict]:
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


def _phase(turn: int) -> str:
    if turn <= 3:
        return "early"
    if turn <= 8:
        return "mid"
    return "late"


def extract_our_features_from_logs(log_range: tuple) -> List[dict]:
    """Extract per-decision features from self-play JSONL logs."""
    start, end = log_range
    features = []
    logs_dir = os.path.join(_REPO_ROOT, "logs")

    for gid in range(start, end):
        path = os.path.join(logs_dir, "game_g%05d.jsonl" % gid)
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                candidates = entry.get("top_candidates") or []
                if len(candidates) < 2:
                    continue

                ss = entry.get("state_summary") or {}
                turn = ss.get("turn", entry.get("game_turn", 0)) or 0

                selected = None
                for c in candidates:
                    if c.get("selected"):
                        selected = c
                        break
                if not selected:
                    selected = candidates[0]

                opt_type = selected.get("option_type", 0)
                has_legal_attack = any(
                    c.get("is_attack") or c.get("option_type") == 13
                    for c in candidates
                )
                is_attack = selected.get("is_attack") or opt_type == 13
                is_end = selected.get("is_end") or opt_type == 14
                is_attach = opt_type == 8
                is_retreat = opt_type == 12

                attach_area = selected.get("inPlayArea") if is_attach else None
                attach_to_active = is_attach and attach_area == _AREA_ACTIVE
                attach_to_bench = is_attach and attach_area == _AREA_BENCH

                active_cid = str(ss.get("active_card_id", ""))
                active_energy = ss.get("active_energy", 0) or 0
                req = _IONO_ENERGY_REQ.get(active_cid, 0)
                active_energy_needed = max(0, req - active_energy) if req > 0 else 0
                is_main_attacker = active_cid in _MAIN_ATTACKERS

                reason = str(selected.get("reason") or selected.get("rule_reason") or "")
                zero_damage = is_attack and ("zero_damage" in reason.lower() or "0_damage" in reason.lower())

                features.append({
                    "turn": turn,
                    "phase": _phase(turn),
                    "action_type": opt_type,
                    "action_name": _ACTION_NAMES.get(opt_type, str(opt_type)),
                    "has_legal_attack": has_legal_attack,
                    "is_attack": is_attack,
                    "is_end": is_end,
                    "is_attach": is_attach,
                    "is_retreat": is_retreat,
                    "attach_to_active": attach_to_active,
                    "attach_to_bench": attach_to_bench,
                    "active_energy_starved": attach_to_bench and active_energy_needed > 0 and is_main_attacker,
                    "attack_when_legal": is_attack and has_legal_attack,
                    "end_when_legal_attack": is_end and has_legal_attack,
                    "zero_damage": zero_damage,
                    "active_card": active_cid,
                    "active_energy_count": active_energy,
                    "active_energy_needed": active_energy_needed,
                    "is_main_attacker": is_main_attacker,
                })

    return features


def aggregate_features(features: List[dict]) -> dict:
    n = len(features)
    if n == 0:
        return {"decisions": 0}

    action_dist = defaultdict(int)
    phase_dist = {"early": defaultdict(int), "mid": defaultdict(int), "late": defaultdict(int)}
    attach_active = sum(1 for f in features if f.get("attach_to_active"))
    attach_bench = sum(1 for f in features if f.get("attach_to_bench"))
    attach_total = attach_active + attach_bench
    starved = sum(1 for f in features if f.get("active_energy_starved"))
    attack_legal = sum(1 for f in features if f.get("has_legal_attack"))
    attack_when_legal = sum(1 for f in features if f.get("attack_when_legal"))
    end_legal_attack = sum(1 for f in features if f.get("end_when_legal_attack"))
    zero_damage = sum(1 for f in features if f.get("zero_damage"))
    retreat_count = sum(1 for f in features if f.get("is_retreat"))

    for f in features:
        name = f.get("action_name", str(f.get("action_type", "")))
        action_dist[name] += 1
        phase = f.get("phase", "late")
        phase_dist[phase][name] += 1

    return {
        "decisions": n,
        "action_distribution": dict(sorted(action_dist.items(), key=lambda x: -x[1])),
        "action_pct": {
            k: round(v / n * 100, 2) for k, v in sorted(action_dist.items(), key=lambda x: -x[1])
        },
        "attach_to_active": attach_active,
        "attach_to_bench": attach_bench,
        "attach_active_rate": round(attach_active / attach_total, 4) if attach_total > 0 else 0.0,
        "active_energy_starved": starved,
        "attack_when_legal": attack_when_legal,
        "attack_legal_total": attack_legal,
        "attack_when_legal_rate": round(attack_when_legal / attack_legal, 4) if attack_legal > 0 else 0.0,
        "end_when_legal_attack": end_legal_attack,
        "end_when_legal_rate": round(end_legal_attack / attack_legal, 4) if attack_legal > 0 else 0.0,
        "zero_damage": zero_damage,
        "retreat_count": retreat_count,
        "retreat_rate": round(retreat_count / n * 100, 2),
        "phase_distribution": {
            p: dict(sorted(phase_dist[p].items(), key=lambda x: -x[1]))
            for p in ["early", "mid", "late"]
        },
    }


def format_comparison_md(label: str, top_agg: dict, our_agg: dict) -> str:
    lines = [f"# Top Episode Comparison: {label}", ""]
    lines.append(f"- Top Episodes: {top_agg['decisions']} decisions")
    lines.append(f"- Our Agent: {our_agg['decisions']} decisions")
    lines.append("")

    lines.append("## Action Distribution")
    lines.append("")
    all_actions = sorted(set(list(top_agg.get("action_pct", {}).keys()) +
                             list(our_agg.get("action_pct", {}).keys())),
                         key=lambda x: -(top_agg.get("action_pct", {}).get(x, 0) +
                                         our_agg.get("action_pct", {}).get(x, 0)))
    lines.append("| Action | Top % | Our % | Gap |")
    lines.append("|--------|-------|-------|-----|")
    for a in all_actions:
        t = top_agg.get("action_pct", {}).get(a, 0)
        o = our_agg.get("action_pct", {}).get(a, 0)
        gap = round(o - t, 2)
        marker = " **" if abs(gap) > 3 else ""
        lines.append(f"| {a} | {t}% | {o}% | {gap:+.2f}{marker} |")

    lines.append("")
    lines.append("## Key Metrics")
    lines.append("")
    lines.append("| Metric | Top | Our | Gap | Priority |")
    lines.append("|--------|-----|-----|-----|----------|")

    metrics = [
        ("Attach to active rate", top_agg.get("attach_active_rate", 0), our_agg.get("attach_active_rate", 0), "high"),
        ("Active energy starved", top_agg.get("active_energy_starved", 0), our_agg.get("active_energy_starved", 0), "high"),
        ("Attack when legal rate", top_agg.get("attack_when_legal_rate", 0), our_agg.get("attack_when_legal_rate", 0), "medium"),
        ("END when legal attack", top_agg.get("end_when_legal_attack", 0), our_agg.get("end_when_legal_attack", 0), "medium"),
        ("zero_damage", top_agg.get("zero_damage", 0), our_agg.get("zero_damage", 0), "high"),
        ("Retreat rate", top_agg.get("retreat_rate", 0), our_agg.get("retreat_rate", 0), "low"),
    ]
    for name, t, o, pri in metrics:
        if isinstance(t, float) and t <= 1:
            lines.append(f"| {name} | {t:.1%} | {o:.1%} | {o-t:+.1%} | {pri} |")
        else:
            lines.append(f"| {name} | {t} | {o} | {o-t:+.0f} | {pri} |")

    lines.append("")
    lines.append("## Phase Distribution")
    lines.append("")
    key_actions = ["ATTACK", "ATTACH", "END", "PLAY", "EVOLVE", "RETREAT"]
    for phase in ["early", "mid", "late"]:
        lines.append(f"### {phase.title()}")
        lines.append("")
        lines.append("| Action | Top | Our |")
        lines.append("|--------|-----|-----|")
        tp = top_agg.get("phase_distribution", {}).get(phase, {})
        op = our_agg.get("phase_distribution", {}).get(phase, {})
        for a in key_actions:
            lines.append(f"| {a} | {tp.get(a, 0)} | {op.get(a, 0)} |")
        lines.append("")

    lines.append("## Remaining Gaps")
    lines.append("")
    gaps = []
    ar_top = top_agg.get("attach_active_rate", 0)
    ar_our = our_agg.get("attach_active_rate", 0)
    if ar_top > 0 and ar_our < ar_top - 0.05:
        gaps.append(("Attach to active rate", f"{ar_our:.1%} vs {ar_top:.1%}", "high"))
    s_top = top_agg.get("active_energy_starved", 0)
    s_our = our_agg.get("active_energy_starved", 0)
    if s_our > s_top + 10:
        gaps.append(("Active energy starved", f"{s_our} vs {s_top}", "high"))
    awl_top = top_agg.get("attack_when_legal_rate", 0)
    awl_our = our_agg.get("attack_when_legal_rate", 0)
    if awl_top > 0 and abs(awl_our - awl_top) > 0.1:
        gaps.append(("Attack when legal", f"{awl_our:.1%} vs {awl_top:.1%}", "medium"))

    if gaps:
        lines.append("| Gap | Values | Priority |")
        lines.append("|-----|--------|----------|")
        for name, vals, pri in gaps:
            lines.append(f"| {name} | {vals} | {pri} |")
    else:
        lines.append("No major gaps found.")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Top Episodes contain multiple deck types - not directly comparable to Iono deck")
    lines.append("- Comparison is for residual analysis, not direct adoption")
    lines.append("- Leaderboard score is the final arbiter")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Compare candidate vs cached Top Episode features"
    )
    parser.add_argument("--top-features", required=True)
    parser.add_argument("--our-features", default="")
    parser.add_argument("--our-logs-range", nargs=2, type=int, metavar=("START", "END"),
                        help="Self-play log range for our agent")
    parser.add_argument("--label", default="candidate")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    t0 = time.time()

    print(f"Loading top features from {args.top_features}...")
    top_feats = load_cached_features(args.top_features)
    print(f"  {len(top_feats)} decisions")

    our_feats = []
    if args.our_logs_range:
        start, end = args.our_logs_range
        print(f"Extracting our features from logs {start}-{end}...")
        our_feats = extract_our_features_from_logs((start, end))
    elif args.our_features:
        print(f"Loading our features from {args.our_features}...")
        our_feats = load_cached_features(args.our_features)

    print(f"  {len(our_feats)} decisions")

    top_agg = aggregate_features(top_feats)
    our_agg = aggregate_features(our_feats)

    md = format_comparison_md(args.label, top_agg, our_agg)

    elapsed = time.time() - t0
    md += f"\n_Comparison completed in {elapsed:.1f}s_\n"

    print(f"\n{md}")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\nSaved to {args.output}")

    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
