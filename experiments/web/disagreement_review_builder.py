"""Extract AI/human MAIN-decision disagreements for manual win-condition review.

This is deliberately NOT an action-value model. The goal is to build a
reviewable, labelable dataset of "moments where AI and human disagreed" so a
human can judge which disagreements actually mattered for winning, before any
learning happens on top of it.

Usage:
    python experiments/web/disagreement_review_builder.py experiments/web/human_traces/
    python experiments/web/disagreement_review_builder.py trace1.jsonl trace2.jsonl \
        --counterfactual experiments/web/counterfactual_analysis.json
"""
import argparse
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from human_trace_writer import load_traces
    from counterfactual_analyzer import _classify, _judge, TYPE_NAMES
except ImportError:
    from experiments.web.human_trace_writer import load_traces
    from experiments.web.counterfactual_analyzer import _classify, _judge, TYPE_NAMES

LABELS = ["human_better", "agent_better", "both_ok", "both_bad", "unclear"]
CONFIDENCES = ["high", "medium", "low"]

DEFAULT_ITEMS_JSON = "experiments/web/disagreement_review_items.json"
DEFAULT_ITEMS_MD = "experiments/web/disagreement_review_items.md"
DEFAULT_LABELS_JSONL = "experiments/web/disagreement_labels.jsonl"

# Risk flags that make an *agreed* pick worth a second look (both AI and
# human walked into the same risk and still lost).
_AGREEMENT_BAD_RISKS = {"no_next_attacker", "active_may_be_ko_next_turn"}

_RISK_PRIORITY_CATEGORIES = {
    "no_next_attacker", "opponent_return_ko_underestimated",
    "boss_missed", "boss_used_too_early", "agreement_bad_risk",
}


def _iter_files(paths):
    files = []
    for path in paths:
        if os.path.isdir(path):
            files.extend(sorted(glob.glob(os.path.join(path, "*.jsonl"))))
        else:
            matched = sorted(glob.glob(path))
            files.extend(matched if matched else [path])
    return [f for f in files if f.endswith(".jsonl")]


def _split_into_games(file_path):
    """Split one trace file into (decisions, game_result_entry_or_None) games."""
    entries = load_traces(file_path)
    games = []
    current = []
    for e in entries:
        etype = e.get("type", "decision")
        if etype == "decision":
            current.append(e)
        elif etype == "game_result":
            games.append((current, e))
            current = []
    if current:
        games.append((current, None))
    return games


def _option_at(options, idx_set):
    return next((o for o in options if o.get("i") in idx_set), None)


def _energy_counter(active_info):
    if not active_info:
        return {}
    out = {}
    for t in (active_info.get("energy_types") or []):
        out[t] = out.get(t, 0) + 1
    return out


def _make_review_id(file_path, game_id, turn, decision_index):
    base = "%s|g%d|t%s|d%d" % (os.path.basename(file_path), game_id, turn, decision_index)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    stem = os.path.splitext(os.path.basename(file_path))[0]
    return "%s_g%d_t%s_d%d_%s" % (stem, game_id, turn, decision_index, digest)


def _build_item(file_path, game_id, decision_index, e, result_win, final_prize_diff,
                 is_agreement_bad):
    options = e.get("options", [])
    ai_pick = set(e.get("ai_pick", []))
    human_pick = set(e.get("human_pick", []))
    ai_opt = _option_at(options, ai_pick) or {}
    human_opt = _option_at(options, human_pick) or {}

    ai_type = TYPE_NAMES.get(ai_opt.get("type", -1), "?")
    human_type = TYPE_NAMES.get(human_opt.get("type", -1), "?")
    ai_score = ai_opt.get("score", 0)
    human_score = human_opt.get("score", 0)

    my = e.get("my_active") or {}
    opp = e.get("opp_active") or {}
    my_prizes = e.get("my_prizes") if e.get("my_prizes") is not None else 6
    opp_prizes = e.get("opp_prizes") if e.get("opp_prizes") is not None else 6
    agent_goals = set(e.get("agent_goals", []))
    agent_risks = set(e.get("agent_risks", []))
    human_risks = set(e.get("risk_flags", []))
    all_risks = human_risks | agent_risks
    turn_goal = e.get("turn_goal", "")

    can_ko = "take_ko_now" in agent_goals
    active_ko_risk = "active_may_be_ko_next_turn" in all_risks
    no_next_attacker_risk = "no_next_attacker" in all_risks
    energy_starved_risk = "not_enough_energy" in all_risks
    next_attacker_ready = (not no_next_attacker_risk) if (human_risks or agent_risks) else None
    boss_win_available = bool(
        "boss_two_prize_target" in (e.get("win_plan_tags") or [])
        or "gust_win_condition" in (e.get("human_reason_tags") or [])
    )

    category = _classify(ai_type, human_type, ai_opt, human_opt, turn_goal,
                          can_ko, active_ko_risk, active_ko_risk,
                          no_next_attacker_risk, my_prizes, opp_prizes, my)
    judgment = _judge(category, ai_type, human_type, can_ko, no_next_attacker_risk,
                       active_ko_risk, active_ko_risk, turn_goal, my_prizes)

    if is_agreement_bad and category == "unknown":
        category = "agreement_bad_risk"
    if is_agreement_bad and judgment == "insufficient_info":
        judgment = "both_bad_or_unclear"

    return {
        "review_id": _make_review_id(file_path, game_id, e.get("turn"), decision_index),
        "source_file": os.path.basename(file_path),
        "game_id": game_id,
        "turn": e.get("turn"),
        "player_index": None,  # not recorded by human_trace_writer today
        "context": e.get("context", ""),
        "decision_index": decision_index,
        "result_win": result_win,
        "final_prize_diff": final_prize_diff,

        "my_prizes": my_prizes,
        "opp_prizes": opp_prizes,
        "prize_diff": my_prizes - opp_prizes,
        "my_active": my.get("name", ""),
        "my_active_hp": my.get("hp"),
        "opp_active": opp.get("name", ""),
        "opp_active_hp": opp.get("hp"),
        "my_bench": None,   # not recorded by human_trace_writer today
        "opp_bench": None,  # not recorded by human_trace_writer today
        "hand_summary": [o.get("label", "") for o in options
                         if o.get("type") in (3, 4, 5, 7)],
        "field_energy_summary": {
            "my_active": _energy_counter(my),
            "opp_active": _energy_counter(opp),
        },
        "discard_summary": None,  # not recorded by human_trace_writer today
        "deck_count": None,       # not recorded by human_trace_writer today
        "current_goal": turn_goal,
        "turn_goal": turn_goal,
        "risk_flags": sorted(all_risks),

        "ai_action": ai_opt.get("label", ""),
        "human_action": human_opt.get("label", ""),
        "ai_action_type": ai_type,
        "human_action_type": human_type,
        "ai_card_id": ai_opt.get("cardId"),
        "human_card_id": human_opt.get("cardId"),
        "ai_score": ai_score,
        "human_score": human_score,
        "score_gap": ai_score - human_score,
        "candidate_actions": [o.get("label", "") for o in options],
        "candidate_scores": [o.get("score", 0) for o in options],

        "category": category,
        "judgment": judgment,
        "reason": e.get("human_reason_tags", []),
        "future_score_estimate": None,  # reserved for the action-value-learning follow-up
        "next_attacker_ready": next_attacker_ready,
        "can_ko_active": can_ko,
        "boss_win_available": boss_win_available,
        "active_ko_risk": active_ko_risk,
        "no_next_attacker_risk": no_next_attacker_risk,
        "energy_starved_risk": energy_starved_risk,

        "is_disagreement": not is_agreement_bad,
        "is_agreement_bad": is_agreement_bad,
    }


def extract_items(file_paths, include_agreement_bad=True):
    """Extract reviewable MAIN-decision items (disagreements + flagged agreements)."""
    items = []
    for fp in file_paths:
        for game_id, (decisions, result_entry) in enumerate(_split_into_games(fp), start=1):
            result_win = None
            if result_entry is not None:
                r = result_entry.get("result")
                result_win = 1 if r == "win" else (0 if r == "loss" else None)

            main_decisions = [d for d in decisions if d.get("context") == "MAIN"]
            final_prize_diff = None
            if main_decisions:
                last = main_decisions[-1]
                mp, op = last.get("my_prizes"), last.get("opp_prizes")
                if mp is not None and op is not None:
                    final_prize_diff = op - mp

            for decision_index, e in enumerate(main_decisions):
                is_disagree = not e.get("agree", False)
                is_agreement_bad = False
                if not is_disagree and include_agreement_bad and result_win == 0:
                    risks = set(e.get("risk_flags", [])) | set(e.get("agent_risks", []))
                    if risks & _AGREEMENT_BAD_RISKS:
                        is_agreement_bad = True
                if not is_disagree and not is_agreement_bad:
                    continue
                items.append(_build_item(fp, game_id, decision_index, e,
                                          result_win, final_prize_diff, is_agreement_bad))
    return items


def _priority_score(item):
    score = abs(item.get("score_gap", 0))
    if item.get("result_win") == 0:
        score += 100
    if item.get("category") in _RISK_PRIORITY_CATEGORIES:
        score += 50
    if item.get("is_agreement_bad"):
        score += 30
    return score


def format_review_item(item, rank=None):
    """Render one item as a human-readable Markdown block."""
    lines = []
    header = "## Review item" + (" #%d" % rank if rank is not None else "")
    lines.append(header + "\n")
    lines.append("Review ID: %s" % item["review_id"])
    lines.append("Game: %s (decision #%d)" % (item["source_file"], item["decision_index"]))
    lines.append("Turn: %s" % item["turn"])
    result = {1: "win", 0: "loss", None: "unknown"}.get(item["result_win"], "unknown")
    lines.append("Result: %s" % result)
    lines.append("Category: %s" % item["category"])
    lines.append("Turn goal: %s\n" % (item["turn_goal"] or "(none)"))

    lines.append("Board:")
    lines.append("- My prizes: %s / Opp prizes: %s" % (item["my_prizes"], item["opp_prizes"]))
    lines.append("- My active: %s HP %s" % (item["my_active"] or "?", item["my_active_hp"]))
    lines.append("- Opp active: %s HP %s" % (item["opp_active"] or "?", item["opp_active_hp"]))
    if item["hand_summary"]:
        lines.append("- Hand-related options: %s" % ", ".join(item["hand_summary"]))
    lines.append("")

    lines.append("AI selected:")
    lines.append("- %s (score=%s)" % (item["ai_action"] or "?", item["ai_score"]))
    lines.append("")
    lines.append("Human selected:")
    lines.append("- %s (score=%s)" % (item["human_action"] or "?", item["human_score"]))
    lines.append("")

    why = []
    if item["no_next_attacker_risk"]:
        why.append("AI attacks now, but next attacker may not be ready")
    if item["active_ko_risk"]:
        why.append("Active Pokemon may be KO'd back next turn")
    if item["boss_win_available"]:
        why.append("A Boss's Orders win line may be available")
    if item["energy_starved_risk"]:
        why.append("Energy attachment is behind schedule")
    if item["is_agreement_bad"]:
        why.append("AI and human agreed, but the game was lost with this risk flagged")
    if not why:
        why.append("Score gap of %s between AI and human picks" % item["score_gap"])
    lines.append("Why this matters:")
    for w in why:
        lines.append("- %s" % w)
    lines.append("")

    lines.append("Suggested review label:")
    lines.append("- human_better / agent_better / both_ok / both_bad / unclear")
    lines.append("")
    lines.append("Reviewer note:")
    lines.append("")
    return "\n".join(lines)


def _count_by(items, key_fn):
    counts = {}
    for it in items:
        k = key_fn(it)
        if k is None:
            continue
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _top_table(lines, title, items, columns, n=20):
    lines.append("\n## %s\n" % title)
    if not items:
        lines.append("(none)\n")
        return
    lines.append("| " + " | ".join(c[0] for c in columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    for it in items[:n]:
        row = [str(c[1](it)) for c in columns]
        row = [v.replace("|", "/") for v in row]
        lines.append("| " + " | ".join(row) + " |")


def format_report(items, total_main_decisions, counterfactual=None):
    disagreements = [it for it in items if it["is_disagreement"]]
    rate = round(100.0 * len(disagreements) / total_main_decisions, 1) if total_main_decisions else 0.0

    lines = ["# Disagreement Review Items\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Total MAIN decisions | %d |" % total_main_decisions)
    lines.append("| Disagreements | %d |" % len(disagreements))
    lines.append("| Disagreement rate | %.1f%% |" % rate)
    lines.append("| Agreement-bad (flagged) | %d |" % sum(1 for it in items if it["is_agreement_bad"]))
    lines.append("| Total review items | %d |" % len(items))

    cats = _count_by(items, lambda it: it["category"])
    if cats:
        lines.append("\n## Category Breakdown\n")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        for cat, cnt in cats.items():
            lines.append("| %s | %d |" % (cat, cnt))

    ai_types = _count_by(items, lambda it: it["ai_action_type"])
    human_types = _count_by(items, lambda it: it["human_action_type"])
    lines.append("\n## Action Type Breakdown\n")
    lines.append("| Type | AI picked | Human picked |")
    lines.append("|------|-----------|--------------|")
    for t in sorted(set(ai_types) | set(human_types)):
        lines.append("| %s | %d | %d |" % (t, ai_types.get(t, 0), human_types.get(t, 0)))

    cards = _count_by(items, lambda it: it["human_action"] or it["ai_action"] or None)
    if cards:
        lines.append("\n## Disagreements by Card / Action\n")
        lines.append("| Action | Count |")
        lines.append("|--------|-------|")
        for c, cnt in list(cards.items())[:20]:
            lines.append("| %s | %d |" % (c, cnt))

    by_gap = sorted(items, key=lambda it: -abs(it["score_gap"]))
    _top_table(lines, "Largest Score Gaps (TOP 20)", by_gap,
               [("Turn", lambda it: it["turn"]), ("Category", lambda it: it["category"]),
                ("AI", lambda it: it["ai_action"]), ("Human", lambda it: it["human_action"]),
                ("Gap", lambda it: it["score_gap"])])

    losses = sorted([it for it in items if it["result_win"] == 0], key=lambda it: -abs(it["score_gap"]))
    _top_table(lines, "Disagreements in Lost Games (TOP 20)", losses,
               [("Turn", lambda it: it["turn"]), ("Category", lambda it: it["category"]),
                ("AI", lambda it: it["ai_action"]), ("Human", lambda it: it["human_action"]),
                ("Final prize diff", lambda it: it["final_prize_diff"])])

    turning = sorted([it for it in items if it["category"] in _RISK_PRIORITY_CATEGORIES],
                      key=lambda it: -_priority_score(it))
    _top_table(lines, "Likely Win/Loss Turning Points (TOP 20)", turning,
               [("Turn", lambda it: it["turn"]), ("Category", lambda it: it["category"]),
                ("Result", lambda it: {1: "win", 0: "loss"}.get(it["result_win"], "?")),
                ("AI", lambda it: it["ai_action"]), ("Human", lambda it: it["human_action"])])

    priority = sorted(items, key=lambda it: -_priority_score(it))[:20]

    lines.append("\n## Priority Review Order (TOP 20)\n")
    lines.append("| Rank | Turn | Category | Result | Priority score |")
    lines.append("|------|------|----------|--------|-----------------|")
    for rank, it in enumerate(priority, start=1):
        lines.append("| %d | %s | %s | %s | %d |" % (
            rank, it["turn"], it["category"],
            {1: "win", 0: "loss"}.get(it["result_win"], "?"), _priority_score(it)))

    if counterfactual and counterfactual.get("recommendations"):
        lines.append("\n## Existing Counterfactual Recommendations (for cross-reference)\n")
        for r in counterfactual["recommendations"]:
            lines.append("- **%s**: %s" % (r.get("target", ""), r.get("issue", "")))

    lines.append("\n## Review Items (Priority Order)\n")
    for rank, it in enumerate(priority, start=1):
        lines.append(format_review_item(it, rank))

    return "\n".join(lines) + "\n"


def build_initial_label(item):
    return {
        "review_id": item["review_id"],
        "game_id": item["game_id"],
        "turn": item["turn"],
        "category": item["category"],
        "ai_action": item["ai_action"],
        "human_action": item["human_action"],
        "label": "",
        "reviewer_note": "",
        "confidence": "",
        "created_from": "human_trace",
    }


def load_labels_jsonl(path):
    records = {}
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("review_id")
            if rid:
                records[rid] = rec
    return records


def merge_labels(existing_path, items):
    """Merge newly-found items into an existing labels file without clobbering
    labels a human has already filled in."""
    existing = load_labels_jsonl(existing_path)
    merged = dict(existing)
    for item in items:
        rid = item["review_id"]
        if rid not in merged:
            merged[rid] = build_initial_label(item)
    return list(merged.values())


def write_labels_jsonl(path, records):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="human_trace JSONL file(s) or directory")
    parser.add_argument("--counterfactual", default="",
                         help="optional path to counterfactual_analysis.json")
    parser.add_argument("--output-json", default=DEFAULT_ITEMS_JSON)
    parser.add_argument("--output-md", default=DEFAULT_ITEMS_MD)
    parser.add_argument("--labels", default=DEFAULT_LABELS_JSONL)
    parser.add_argument("--no-agreement-bad", action="store_true")
    args = parser.parse_args()

    files = _iter_files(args.paths)
    items = extract_items(files, include_agreement_bad=not args.no_agreement_bad)

    total_main = 0
    for fp in files:
        for decisions, _ in _split_into_games(fp):
            total_main += sum(1 for d in decisions if d.get("context") == "MAIN")

    counterfactual = None
    if args.counterfactual and os.path.exists(args.counterfactual):
        with open(args.counterfactual, encoding="utf-8") as f:
            counterfactual = json.load(f)

    os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    os.makedirs(os.path.dirname(args.output_md) or ".", exist_ok=True)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(format_report(items, total_main, counterfactual))

    labels = merge_labels(args.labels, items)
    write_labels_jsonl(args.labels, labels)

    print("Review items: %d -> %s, %s" % (len(items), args.output_json, args.output_md))
    print("Labels: %d -> %s" % (len(labels), args.labels))


if __name__ == "__main__":
    main()
