"""
Generate before/after learning report in Markdown.
"""
from __future__ import annotations
from typing import Dict, List


def generate_report(
    logs: List[dict],
    weights_before: Dict[str, float],
    weights_after: Dict[str, float],
    stats_before: dict,
    stats_after: dict,
) -> str:
    lines = ["# Learning Report", ""]

    # --- Result Breakdown ---
    wins = sum(1 for e in logs if e.get("result", {}).get("win"))
    losses = sum(1 for e in logs if not e.get("result", {}).get("win"))
    bricked = sum(1 for e in logs if e.get("result", {}).get("starting_hand_bricked"))
    prizes_list = [e.get("result", {}).get("prizes_taken", 0) for e in logs if e.get("result", {}).get("prizes_taken") is not None]
    avg_prizes = round(sum(prizes_list) / len(prizes_list), 2) if prizes_list else 0.0
    win_turns = [e.get("result", {}).get("turns_to_win", 0) for e in logs if e.get("result", {}).get("win") and e.get("result", {}).get("turns_to_win")]
    avg_win_turns = round(sum(win_turns) / len(win_turns), 2) if win_turns else 0.0

    lines.append("## Result Breakdown")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Win entries | %d |" % wins)
    lines.append("| Loss entries | %d |" % losses)
    lines.append("| Bricked entries | %d |" % bricked)
    lines.append("| Average prizes taken | %.2f |" % avg_prizes)
    lines.append("| Average turns to win | %.2f |" % avg_win_turns)
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Before | After | Change |")
    lines.append("|--------|--------|-------|--------|")
    acc_b = stats_before.get("accuracy", 0) * 100
    acc_a = stats_after.get("accuracy", 0) * 100
    lines.append("| Accuracy | %.1f%% | %.1f%% | %+.1f%% |" % (acc_b, acc_a, acc_a - acc_b))
    rank_b = stats_before.get("avg_rank", 0)
    rank_a = stats_after.get("avg_rank", 0)
    lines.append("| Avg Rank | %.2f | %.2f | %+.2f |" % (rank_b, rank_a, rank_a - rank_b))
    lines.append("| Log entries | %d | %d | - |" % (stats_before.get("total", 0), stats_after.get("total", 0)))
    lines.append("")

    all_keys = sorted(set(list(weights_before.keys()) + list(weights_after.keys())))
    increased = []
    decreased = []
    unchanged = []
    for k in all_keys:
        before = weights_before.get(k, 0.0)
        after = weights_after.get(k, 0.0)
        diff = after - before
        if abs(diff) < 0.001:
            unchanged.append((k, before, after, diff))
        elif diff > 0:
            increased.append((k, before, after, diff))
        else:
            decreased.append((k, before, after, diff))

    if increased:
        lines.append("## Increased Weights")
        lines.append("")
        lines.append("| Weight | Before | After | Change |")
        lines.append("|--------|--------|-------|--------|")
        for k, b, a, d in sorted(increased, key=lambda x: -x[3]):
            lines.append("| %s | %.2f | %.2f | %+.2f |" % (k, b, a, d))
        lines.append("")

    if decreased:
        lines.append("## Decreased Weights")
        lines.append("")
        lines.append("| Weight | Before | After | Change |")
        lines.append("|--------|--------|-------|--------|")
        for k, b, a, d in sorted(decreased, key=lambda x: x[3]):
            lines.append("| %s | %.2f | %.2f | %+.2f |" % (k, b, a, d))
        lines.append("")

    from experiments.learning.evaluator import evaluate_log_entry
    archetypes: Dict[str, Dict] = {}
    opp_archetypes: Dict[str, Dict] = {}
    for entry in logs:
        arch = entry.get("deck_archetype", "unknown")
        opp = entry.get("opponent_archetype", "unknown")
        archetypes.setdefault(arch, {"total": 0, "match": 0})
        opp_archetypes.setdefault(opp, {"total": 0, "match": 0})
        result = evaluate_log_entry(entry, weights_after)
        if result["rank"] >= 0:
            archetypes[arch]["total"] += 1
            opp_archetypes[opp]["total"] += 1
            if result["match"]:
                archetypes[arch]["match"] += 1
                opp_archetypes[opp]["match"] += 1

    if archetypes:
        lines.append("## By Deck Archetype")
        lines.append("")
        lines.append("| Archetype | Entries | Accuracy |")
        lines.append("|-----------|---------|----------|")
        for arch, s in sorted(archetypes.items()):
            acc = "%.1f%%" % (s["match"] / s["total"] * 100) if s["total"] else "N/A"
            lines.append("| %s | %d | %s |" % (arch, s["total"], acc))
        lines.append("")

    if len(opp_archetypes) > 1:
        lines.append("## By Opponent Archetype")
        lines.append("")
        lines.append("| Opponent | Entries | Accuracy |")
        lines.append("|----------|---------|----------|")
        for opp, s in sorted(opp_archetypes.items()):
            acc = "%.1f%%" % (s["match"] / s["total"] * 100) if s["total"] else "N/A"
            lines.append("| %s | %d | %s |" % (opp, s["total"], acc))
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Unchanged weights: %d" % len(unchanged))
    lines.append("- Total weight keys: %d" % len(all_keys))
    lines.append("")

    return "\n".join(lines)
