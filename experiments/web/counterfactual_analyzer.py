"""Counterfactual analysis: identify which AI-human disagreements
matter for win rate, not just agreement rate.

Usage:
    python experiments/web/counterfactual_analyzer.py experiments/web/human_traces/
    python experiments/web/counterfactual_analyzer.py trace1.jsonl trace2.jsonl
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

try:
    from human_trace_writer import load_traces
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from human_trace_writer import load_traces


TYPE_NAMES = {7: "PLAY", 8: "ATTACH", 10: "ABILITY", 12: "RETREAT", 13: "ATTACK", 14: "END"}

C_RAGING_BOLT = 63
C_OGERPON = 96
C_CRISPIN = 1198
C_LILLIE = 1227
C_BOSS = 1182


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


def analyze_counterfactual(entries):
    decisions = [e for e in entries if e.get("type", "decision") == "decision"]
    results = [e for e in entries if e.get("type") == "game_result"]
    main_disagrees = [
        e for e in decisions
        if e.get("context") == "MAIN" and not e.get("agree", False)
    ]
    main_total = [e for e in decisions if e.get("context") == "MAIN"]
    main_agree = sum(1 for e in main_total if e.get("agree", False))

    cases = []
    for e in main_disagrees:
        case = _build_case(e)
        cases.append(case)

    categories = Counter(c["category"] for c in cases)
    judgments = Counter(c["judgment"] for c in cases)

    card_gaps = _card_score_gaps(cases)
    eval_breakdown = _eval_state_breakdown(main_disagrees)
    recommendations = _build_recommendations(cases, categories, card_gaps)

    human_better = [c for c in cases if c["judgment"] == "human_likely_better"]
    ai_better = [c for c in cases if c["judgment"] == "ai_likely_better"]
    human_better.sort(key=lambda c: -c["score_gap"])
    ai_better.sort(key=lambda c: -c["score_gap"])

    return {
        "games": {"wins": sum(1 for r in results if r.get("result") == "win"),
                  "losses": sum(1 for r in results if r.get("result") == "loss"),
                  "total": len(results)},
        "decisions": {"total": len(decisions), "main": len(main_total),
                      "main_agree": main_agree, "main_disagree": len(main_disagrees),
                      "main_agree_pct": round(100 * main_agree / len(main_total), 1) if main_total else 0},
        "categories": dict(categories.most_common(20)),
        "judgments": dict(judgments.most_common()),
        "human_likely_better": [_summarize_case(c) for c in human_better[:15]],
        "ai_likely_better": [_summarize_case(c) for c in ai_better[:15]],
        "card_score_gaps": card_gaps,
        "eval_breakdown_avg": eval_breakdown,
        "recommendations": recommendations,
    }


def _build_case(e):
    options = e.get("options", [])
    ai_pick = set(e.get("ai_pick", []))
    human_pick = set(e.get("human_pick", []))

    ai_opt = next((o for o in options if o.get("i") in ai_pick), None)
    human_opt = next((o for o in options if o.get("i") in human_pick), None)

    ai_type = TYPE_NAMES.get(ai_opt.get("type", -1), "?") if ai_opt else "?"
    human_type = TYPE_NAMES.get(human_opt.get("type", -1), "?") if human_opt else "?"
    ai_score = ai_opt.get("score", 0) if ai_opt else 0
    human_score = human_opt.get("score", 0) if human_opt else 0

    my = e.get("my_active") or {}
    opp = e.get("opp_active") or {}
    my_prizes = e.get("my_prizes") or 6
    opp_prizes = e.get("opp_prizes") or 6
    agent_goals = set(e.get("agent_goals", []))
    agent_risks = set(e.get("agent_risks", []))
    human_risks = set(e.get("risk_flags", []))
    turn_goal = e.get("turn_goal", "")

    can_ko = "take_ko_now" in agent_goals
    active_ko_risk_human = "active_may_be_ko_next_turn" in human_risks
    active_ko_risk_agent = "active_may_be_ko_next_turn" in agent_risks
    no_next_attacker = "no_next_attacker" in human_risks or "no_next_attacker" in agent_risks

    category = _classify(ai_type, human_type, ai_opt, human_opt, turn_goal,
                          can_ko, active_ko_risk_human, active_ko_risk_agent,
                          no_next_attacker, my_prizes, opp_prizes, my)
    judgment = _judge(category, ai_type, human_type, can_ko, no_next_attacker,
                       active_ko_risk_human, active_ko_risk_agent, turn_goal, my_prizes)

    return {
        "turn": e.get("turn"),
        "ai_label": ai_opt.get("label", "") if ai_opt else "",
        "ai_type": ai_type,
        "ai_score": ai_score,
        "human_label": human_opt.get("label", "") if human_opt else "",
        "human_type": human_type,
        "human_score": human_score,
        "score_gap": ai_score - human_score,
        "turn_goal": turn_goal,
        "agent_goals": sorted(agent_goals),
        "agent_risks": sorted(agent_risks),
        "human_risks": sorted(human_risks),
        "my_prizes": my_prizes,
        "opp_prizes": opp_prizes,
        "my_hp": my.get("hp", 0),
        "my_maxhp": my.get("maxHp", 0),
        "opp_hp": opp.get("hp", 0),
        "can_ko": can_ko,
        "no_next_attacker": no_next_attacker,
        "active_ko_risk_human": active_ko_risk_human,
        "active_ko_risk_agent": active_ko_risk_agent,
        "category": category,
        "judgment": judgment,
    }


def _classify(ai_type, human_type, ai_opt, human_opt, turn_goal,
              can_ko, active_ko_risk_human, active_ko_risk_agent,
              no_next_attacker, my_prizes, opp_prizes, my_active):
    if no_next_attacker and human_type == "PLAY":
        return "no_next_attacker"
    if active_ko_risk_human and not active_ko_risk_agent:
        return "opponent_return_ko_underestimated"
    if ai_type == "ATTACK" and human_type == "PLAY":
        return "attack_too_early"
    if ai_type == "PLAY" and human_type == "ATTACK":
        return "attack_too_late"
    if ai_type == "ATTACK" and human_type == "ABILITY":
        return "attack_too_early"
    if ai_type == "ATTACK" and human_type == "END":
        return "end_turn_bad"
    if human_type == "END" and ai_type != "END":
        return "end_turn_bad"
    if ai_type == "ATTACH" and human_type == "PLAY":
        return "setup_too_slow"
    if human_type == "RETREAT" and ai_type != "RETREAT":
        return "opponent_return_ko_underestimated"
    ai_cid = (ai_opt or {}).get("cardId")
    human_cid = (human_opt or {}).get("cardId")
    if ai_cid == C_BOSS and turn_goal != "take_two_prizes":
        return "boss_used_too_early"
    if human_cid == C_BOSS and can_ko:
        return "boss_missed"
    if ai_type == "ATTACK" and (ai_opt or {}).get("attackId") == 71:
        return "hand_refresh_overvalued"
    return "unknown"


def _judge(category, ai_type, human_type, can_ko, no_next_attacker,
            active_ko_risk_human, active_ko_risk_agent, turn_goal, my_prizes):
    if category == "attack_too_early":
        return "human_likely_better"
    if category == "attack_too_late" and can_ko:
        return "ai_likely_better"
    if category == "attack_too_late":
        return "both_bad_or_unclear"
    if category == "setup_too_slow":
        return "human_likely_better"
    if category == "no_next_attacker":
        return "human_likely_better"
    if category == "opponent_return_ko_underestimated":
        return "human_likely_better"
    if category == "end_turn_bad":
        if human_type == "END":
            return "both_bad_or_unclear"
        return "ai_likely_better"
    if category == "boss_missed":
        return "human_likely_better"
    if category == "boss_used_too_early":
        return "human_likely_better"
    if category == "hand_refresh_overvalued":
        return "human_likely_better"
    return "insufficient_info"


def _card_score_gaps(cases):
    gaps = defaultdict(lambda: {"count": 0, "total_gap": 0})
    for c in cases:
        for keyword in ["Crispin", "Lillie", "Boss", "Ultra Ball", "Pokégear",
                         "Bug Catching", "Tera Orb", "Energy Retrieval",
                         "Bellowing Thunder", "Myriad Leaf", "Burst Roar",
                         "Teal Dance", "Teal Mask Ogerpon", "Raging Bolt",
                         "ターン終了", "にげる"]:
            if keyword in c["human_label"] or keyword in c["ai_label"]:
                gaps[keyword]["count"] += 1
                gaps[keyword]["total_gap"] += c["score_gap"]
                break
    result = {}
    for card, info in gaps.items():
        if info["count"] >= 2:
            result[card] = {
                "count": info["count"],
                "avg_gap": round(info["total_gap"] / info["count"], 0),
            }
    return dict(sorted(result.items(), key=lambda x: -x[1]["count"]))


def _eval_state_breakdown(main_disagrees):
    totals = defaultdict(lambda: {"count": 0, "total": 0})
    for e in main_disagrees:
        my = e.get("my_active") or {}
        opp = e.get("opp_active") or {}
        my_prizes = e.get("my_prizes") or 6
        opp_prizes = e.get("opp_prizes") or 6

        def add(key, val):
            totals[key]["count"] += 1
            totals[key]["total"] += val

        add("prize_plan", (6 - my_prizes) * 200 - (6 - opp_prizes) * 150)
        add("ko_pressure", 500 if e.get("agree") is False and "take_ko_now" in set(e.get("agent_goals", [])) else 0)
        add("hand_quality", min(len(e.get("options", [])), 7) * 30)
        hp = my.get("hp", 240)
        maxhp = my.get("maxHp", 240)
        add("survival", -300 if hp <= 120 else 0)

    result = {}
    for key, info in totals.items():
        if info["count"] > 0:
            result[key] = round(info["total"] / info["count"], 0)
    return result


def _build_recommendations(cases, categories, card_gaps):
    recs = []

    if categories.get("attack_too_early", 0) >= 3:
        recs.append({
            "target": "ATTACK cap / _score_attack",
            "issue": "attack_too_early: %d cases" % categories["attack_too_early"],
            "suggestion": "PLAY/ABILITY が残っている場面で攻撃スコアが高すぎる。cap を 900 から下げるか、サポーター未使用時のペナルティを追加",
            "param_candidates": ["search_weight_immediate", "impact_bt_ko_prize_mult"],
        })

    if categories.get("opponent_return_ko_underestimated", 0) >= 3:
        recs.append({
            "target": "eval_active_ko_risk / _estimate_opp_damage",
            "issue": "opponent_return_ko_underestimated: %d cases" % categories["opponent_return_ko_underestimated"],
            "suggestion": "eval_active_ko_risk を -200 から -400 程度に強めるか、_estimate_opp_damage の閾値を下げる",
            "param_candidates": ["eval_active_ko_risk", "eval_no_backup_risk"],
        })

    if categories.get("no_next_attacker", 0) >= 2:
        recs.append({
            "target": "eval_no_backup_risk / _detect_strategy",
            "issue": "no_next_attacker: %d cases" % categories["no_next_attacker"],
            "suggestion": "eval_no_backup_risk を強めるか、ベンチ Bolt 展開の優先度を上げる",
            "param_candidates": ["eval_no_backup_risk", "impact_play_bolt"],
        })

    if categories.get("setup_too_slow", 0) >= 2:
        recs.append({
            "target": "setup_board bonus / search item scores",
            "issue": "setup_too_slow: %d cases" % categories["setup_too_slow"],
            "suggestion": "セットアップ未完時のサーチアイテムスコアをさらに上げる",
            "param_candidates": ["score_item_ultra_ball", "score_item_bug_catching_set"],
        })

    for card, info in list(card_gaps.items())[:5]:
        if info["avg_gap"] > 300 and info["count"] >= 3:
            recs.append({
                "target": "_score_play / %s" % card,
                "issue": "%s: %d disagreements, avg gap=%.0f" % (card, info["count"], info["avg_gap"]),
                "suggestion": "%s のスコアが AI で高すぎるか人間で低すぎる" % card,
                "param_candidates": [],
            })

    return recs


def _summarize_case(c):
    return {
        "turn": c["turn"],
        "ai": "%s (%s, score=%d)" % (c["ai_label"][:40], c["ai_type"], c["ai_score"]),
        "human": "%s (%s, score=%d)" % (c["human_label"][:40], c["human_type"], c["human_score"]),
        "gap": c["score_gap"],
        "category": c["category"],
        "goal": c["turn_goal"],
        "prizes": "%d-%d" % (c["my_prizes"], c["opp_prizes"]),
    }


def format_report(analysis):
    lines = ["# Counterfactual Analysis Report\n"]

    lines.append("## Summary\n")
    g = analysis["games"]
    d = analysis["decisions"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Games | %d (W:%d L:%d) |" % (g["total"], g["wins"], g["losses"]))
    lines.append("| Decisions | %d |" % d["total"])
    lines.append("| MAIN agree | %d/%d (%.1f%%) |" % (d["main_agree"], d["main"], d["main_agree_pct"]))
    lines.append("| MAIN disagree | %d |" % d["main_disagree"])

    cats = analysis.get("categories", {})
    if cats:
        lines.append("\n## Disagreement Categories\n")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (cat, cnt))

    judg = analysis.get("judgments", {})
    if judg:
        lines.append("\n## Judgments\n")
        lines.append("| Judgment | Count |")
        lines.append("|----------|-------|")
        for j, cnt in sorted(judg.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (j, cnt))

    hb = analysis.get("human_likely_better", [])
    if hb:
        lines.append("\n## Human Likely Better (TOP %d)\n" % len(hb))
        lines.append("| Turn | Category | Goal | AI | Human | Gap | Prizes |")
        lines.append("|------|----------|------|----|-------|-----|--------|")
        for c in hb[:10]:
            lines.append("| %s | %s | %s | %s | %s | %d | %s |" % (
                c["turn"], c["category"], c.get("goal", ""),
                c["ai"][:30], c["human"][:30], c["gap"], c["prizes"]))

    ab = analysis.get("ai_likely_better", [])
    if ab:
        lines.append("\n## AI Likely Better (TOP %d)\n" % len(ab))
        lines.append("| Turn | Category | AI | Human | Gap |")
        lines.append("|------|----------|----|-------|-----|")
        for c in ab[:10]:
            lines.append("| %s | %s | %s | %s | %d |" % (
                c["turn"], c["category"], c["ai"][:30], c["human"][:30], c["gap"]))

    gaps = analysis.get("card_score_gaps", {})
    if gaps:
        lines.append("\n## Card/Action Score Gaps\n")
        lines.append("| Card | Count | Avg Gap |")
        lines.append("|------|-------|---------|")
        for card, info in gaps.items():
            lines.append("| %s | %d | %.0f |" % (card, info["count"], info["avg_gap"]))

    eb = analysis.get("eval_breakdown_avg", {})
    if eb:
        lines.append("\n## Evaluate State Breakdown (disagree avg)\n")
        lines.append("| Component | Avg Score |")
        lines.append("|-----------|-----------|")
        for comp, val in eb.items():
            lines.append("| %s | %.0f |" % (comp, val))

    recs = analysis.get("recommendations", [])
    if recs:
        lines.append("\n## Recommendations\n")
        for r in recs:
            lines.append("### %s\n" % r["target"])
            lines.append("**Issue:** %s\n" % r["issue"])
            lines.append("**Suggestion:** %s\n" % r["suggestion"])
            if r.get("param_candidates"):
                lines.append("**Param candidates:** %s\n" % ", ".join(r["param_candidates"]))

    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: python counterfactual_analyzer.py <trace.jsonl|dir> [more...]")
        sys.exit(1)

    entries = _load_all(sys.argv[1:])
    analysis = analyze_counterfactual(entries)

    with open("counterfactual_analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    with open("counterfactual_analysis.md", "w", encoding="utf-8") as f:
        f.write(format_report(analysis))

    print("Saved: counterfactual_analysis.json, counterfactual_analysis.md")
    print("MAIN disagrees: %d" % analysis["decisions"]["main_disagree"])
    cats = analysis.get("categories", {})
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1])[:5]:
        print("  %s: %d" % (cat, cnt))


if __name__ == "__main__":
    main()
