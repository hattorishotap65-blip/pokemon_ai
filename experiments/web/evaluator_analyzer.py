"""Analyze human traces and simulation logs to find evaluate_state /
_estimate_action_impact / _simulate_opponent_turn improvement candidates.

Usage:
    python experiments/web/evaluator_analyzer.py experiments/web/human_traces/
    python experiments/web/evaluator_analyzer.py trace1.jsonl trace2.jsonl

Outputs:
    evaluator_analysis.json
    evaluator_analysis.md
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

try:
    from human_trace_writer import load_traces
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from human_trace_writer import load_traces


def _load_all(paths):
    entries = []
    for path in paths:
        if os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "*.jsonl")))
        else:
            files = sorted(glob.glob(path)) or [path]
        for fp in files:
            if fp.endswith(".jsonl"):
                entries.extend(load_traces(fp))
    return entries


def analyze_evaluator(entries):
    decisions = [e for e in entries if e.get("type", "decision") == "decision"]
    results = [e for e in entries if e.get("type") == "game_result"]

    wins = [r for r in results if r.get("result") == "win"]
    losses = [r for r in results if r.get("result") == "loss"]

    # Group decisions by game (by trace file proximity to game_result)
    main_decisions = [e for e in decisions if e.get("context") == "MAIN"]

    analysis = {
        "games": {"wins": len(wins), "losses": len(losses), "total": len(wins) + len(losses)},
        "decisions": {"total": len(decisions), "main": len(main_decisions)},
    }

    # 1. Action type distribution in disagree cases
    TYPE_NAMES = {7: "PLAY", 8: "ATTACH", 10: "ABILITY", 12: "RETREAT", 13: "ATTACK", 14: "END"}
    human_type = Counter()
    ai_type = Counter()
    disagree_by_card = Counter()
    disagree_details = []

    for e in main_decisions:
        if e.get("agree"):
            continue
        options = e.get("options", [])
        ai_pick = set(e.get("ai_pick", []))
        human_pick = set(e.get("human_pick", []))

        for opt in options:
            i = opt.get("i")
            otype = TYPE_NAMES.get(opt.get("type", -1), str(opt.get("type")))
            if i in human_pick:
                human_type[otype] += 1
            if i in ai_pick:
                ai_type[otype] += 1

        for i in human_pick - ai_pick:
            opt = next((o for o in options if o.get("i") == i), None)
            if opt:
                label = opt.get("label", "")
                score = opt.get("score", 0)
                ai_top = max((o.get("score", 0) for o in options), default=0)
                disagree_by_card[label] += 1
                disagree_details.append({
                    "turn": e.get("turn"),
                    "human_label": label,
                    "human_score": score,
                    "ai_top_score": ai_top,
                    "gap": ai_top - score,
                    "turn_goal": e.get("turn_goal", ""),
                    "risks": e.get("risk_flags", []),
                    "my_active": e.get("my_active"),
                    "opp_active": e.get("opp_active"),
                    "my_prizes": e.get("my_prizes"),
                    "opp_prizes": e.get("opp_prizes"),
                })

    analysis["action_type_gap"] = {
        t: {"human": human_type.get(t, 0), "ai": ai_type.get(t, 0),
            "diff": human_type.get(t, 0) - ai_type.get(t, 0)}
        for t in sorted(set(list(human_type.keys()) + list(ai_type.keys())))
    }

    # 2. evaluate_state signals
    eval_signals = _analyze_eval_signals(main_decisions)
    analysis["eval_signals"] = eval_signals

    # 3. action_impact candidates
    impact_candidates = _analyze_action_impact(disagree_details)
    analysis["impact_candidates"] = impact_candidates

    # 4. opponent model gaps
    opp_gaps = _analyze_opponent_model(main_decisions)
    analysis["opponent_model_gaps"] = opp_gaps

    # 5. Build improvement recommendations
    analysis["recommendations"] = _build_recommendations(analysis)

    return analysis


def _analyze_eval_signals(main_decisions):
    """Check which board states correlate with human disagreement."""
    signals = defaultdict(lambda: {"agree": 0, "disagree": 0})

    for e in main_decisions:
        is_agree = e.get("agree", False)
        key = "agree" if is_agree else "disagree"

        my = e.get("my_active") or {}
        opp = e.get("opp_active") or {}
        my_prizes = e.get("my_prizes") or 6
        opp_prizes = e.get("opp_prizes") or 6

        if my.get("hp", 999) <= 120:
            signals["active_low_hp"][key] += 1
        if my_prizes <= 2:
            signals["close_to_winning"][key] += 1
        if my_prizes > opp_prizes + 1:
            signals["behind_prize_race"][key] += 1
        if my.get("energy", 0) == 0:
            signals["no_energy_active"][key] += 1
        if opp.get("hp", 0) <= 70:
            signals["opp_low_hp"][key] += 1
        if opp.get("ex"):
            signals["opp_is_ex"][key] += 1

        agent_goals = set(e.get("agent_goals", []))
        human_goal = e.get("turn_goal", "")
        if "take_ko_now" in agent_goals and human_goal != "take_ko_now":
            signals["agent_ko_human_not"][key] += 1
        if human_goal == "take_ko_now" and "take_ko_now" not in agent_goals:
            signals["human_ko_agent_not"][key] += 1

    result = {}
    for sig, counts in signals.items():
        total = counts["agree"] + counts["disagree"]
        if total < 3:
            continue
        disagree_rate = counts["disagree"] / total if total > 0 else 0
        result[sig] = {
            "agree": counts["agree"],
            "disagree": counts["disagree"],
            "total": total,
            "disagree_rate": round(disagree_rate * 100, 1),
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]["disagree_rate"]))


def _analyze_action_impact(disagree_details):
    """Find which card/action types have largest score gaps."""
    card_gaps = defaultdict(lambda: {"count": 0, "total_gap": 0, "turns": []})

    for d in disagree_details:
        label = d["human_label"]
        # Simplify label
        for keyword in ["Crispin", "Lillie", "Boss", "Ultra Ball", "Pokégear",
                         "Bug Catching", "Tera Orb", "Energy Retrieval",
                         "Bellowing Thunder", "Myriad Leaf", "Burst Roar",
                         "Teal Dance", "Teal Mask Ogerpon", "Raging Bolt",
                         "ターン終了", "にげる"]:
            if keyword in label:
                card_gaps[keyword]["count"] += 1
                card_gaps[keyword]["total_gap"] += d["gap"]
                card_gaps[keyword]["turns"].append(d["turn"])
                break

    result = {}
    for card, info in card_gaps.items():
        if info["count"] < 2:
            continue
        avg_gap = info["total_gap"] / info["count"]
        direction = "increase" if avg_gap > 0 else "decrease"
        result[card] = {
            "count": info["count"],
            "avg_gap": round(avg_gap, 0),
            "direction": direction,
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]["count"]))


def _analyze_opponent_model(main_decisions):
    """Find cases where opponent risk was under/over-estimated."""
    gaps = {
        "active_ko_missed": 0,
        "active_ko_false": 0,
        "boss_risk_missed": 0,
    }

    for e in main_decisions:
        agent_risks = set(e.get("agent_risks", []))
        human_risks = set(e.get("risk_flags", []))

        if "active_may_be_ko_next_turn" in human_risks and "active_may_be_ko_next_turn" not in agent_risks:
            gaps["active_ko_missed"] += 1
        if "active_may_be_ko_next_turn" in agent_risks and "active_may_be_ko_next_turn" not in human_risks:
            gaps["active_ko_false"] += 1
        if "no_next_attacker" in human_risks and "no_next_attacker" not in agent_risks:
            gaps["boss_risk_missed"] += 1

    return gaps


def _build_recommendations(analysis):
    recs = []
    type_gap = analysis.get("action_type_gap", {})

    attack_gap = type_gap.get("ATTACK", {})
    if attack_gap.get("diff", 0) < -1:
        recs.append({
            "target": "_estimate_action_impact / ATTACK",
            "issue": "AI selects ATTACK %d more times than human" % abs(attack_gap["diff"]),
            "suggestion": "ATTACK の future_delta や immediate score が高すぎる可能性。攻撃前にPLAY/ABILITYを使い切るべき",
            "priority": "high",
        })

    play_gap = type_gap.get("PLAY", {})
    if play_gap.get("diff", 0) > 1:
        recs.append({
            "target": "_estimate_action_impact / PLAY",
            "issue": "Human selects PLAY %d more times than AI" % play_gap["diff"],
            "suggestion": "PLAY (アイテム/サポーター) の future_delta が低すぎる可能性",
            "priority": "high",
        })

    eval_sigs = analysis.get("eval_signals", {})
    for sig, info in eval_sigs.items():
        if info["disagree_rate"] >= 60 and info["total"] >= 5:
            recs.append({
                "target": "evaluate_state / %s" % sig,
                "issue": "Disagree rate %.0f%% (%d/%d) in '%s' situations" % (
                    info["disagree_rate"], info["disagree"], info["total"], sig),
                "suggestion": "この盤面状態での評価値が不適切な可能性",
                "priority": "medium",
            })

    opp = analysis.get("opponent_model_gaps", {})
    if opp.get("active_ko_missed", 0) >= 1:
        recs.append({
            "target": "_simulate_opponent_turn / active KO",
            "issue": "Agent missed active KO risk %d times" % opp["active_ko_missed"],
            "suggestion": "_estimate_opp_damage の閾値が高すぎるか、弱点計算が抜けている",
            "priority": "high",
        })
    if opp.get("active_ko_false", 0) >= 1:
        recs.append({
            "target": "_simulate_opponent_turn / active KO",
            "issue": "Agent false-positive active KO risk %d times" % opp["active_ko_false"],
            "suggestion": "_estimate_opp_damage が過大評価している",
            "priority": "medium",
        })

    impact = analysis.get("impact_candidates", {})
    for card, info in list(impact.items())[:5]:
        if info["avg_gap"] > 200:
            recs.append({
                "target": "_estimate_action_impact / %s" % card,
                "issue": "%s: human chose %dx, avg gap=%.0f, needs %s" % (
                    card, info["count"], info["avg_gap"], info["direction"]),
                "suggestion": "%s の future_delta を %s すべき" % (card, info["direction"]),
                "priority": "medium",
            })

    return sorted(recs, key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r["priority"], 3))


def format_report(analysis):
    lines = ["# Evaluator Analysis Report\n"]

    games = analysis.get("games", {})
    lines.append("## Games\n")
    lines.append("Wins: %d, Losses: %d\n" % (games.get("wins", 0), games.get("losses", 0)))

    lines.append("## Action Type Gap (MAIN disagrees)\n")
    lines.append("| Type | Human | AI | Diff |")
    lines.append("|------|-------|-----|------|")
    for t, info in analysis.get("action_type_gap", {}).items():
        lines.append("| %s | %d | %d | %+d |" % (t, info["human"], info["ai"], info["diff"]))

    sigs = analysis.get("eval_signals", {})
    if sigs:
        lines.append("\n## Board State Disagree Rates\n")
        lines.append("| State | Agree | Disagree | Rate |")
        lines.append("|-------|-------|----------|------|")
        for sig, info in sigs.items():
            lines.append("| %s | %d | %d | %.0f%% |" % (sig, info["agree"], info["disagree"], info["disagree_rate"]))

    impact = analysis.get("impact_candidates", {})
    if impact:
        lines.append("\n## Action Impact Candidates\n")
        lines.append("| Card/Action | Count | Avg Gap | Direction |")
        lines.append("|-------------|-------|---------|-----------|")
        for card, info in impact.items():
            lines.append("| %s | %d | %.0f | %s |" % (card, info["count"], info["avg_gap"], info["direction"]))

    opp = analysis.get("opponent_model_gaps", {})
    if opp:
        lines.append("\n## Opponent Model Gaps\n")
        lines.append("| Issue | Count |")
        lines.append("|-------|-------|")
        for k, v in opp.items():
            if v > 0:
                lines.append("| %s | %d |" % (k, v))

    recs = analysis.get("recommendations", [])
    if recs:
        lines.append("\n## Recommendations\n")
        lines.append("| Priority | Target | Issue | Suggestion |")
        lines.append("|----------|--------|-------|------------|")
        for r in recs:
            lines.append("| %s | %s | %s | %s |" % (
                r["priority"], r["target"],
                r["issue"].replace("|", "\\|"),
                r["suggestion"].replace("|", "\\|")))

    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluator_analyzer.py <trace.jsonl|dir> [more...]")
        sys.exit(1)

    entries = _load_all(sys.argv[1:])
    analysis = analyze_evaluator(entries)

    out_json = "evaluator_analysis.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    out_md = "evaluator_analysis.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(format_report(analysis))

    print("Saved: %s, %s" % (out_json, out_md))
    recs = analysis.get("recommendations", [])
    print("Recommendations: %d" % len(recs))
    for r in recs:
        print("  [%s] %s: %s" % (r["priority"], r["target"], r["issue"]))


if __name__ == "__main__":
    main()
