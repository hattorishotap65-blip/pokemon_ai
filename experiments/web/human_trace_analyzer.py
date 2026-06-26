"""Analyze human play traces vs AI recommendations.

Reads JSONL trace files and computes:
- Agreement rate (human == AI)
- Disagreements by option_type, card_id, context
- Cases where human chose low-AI-score options
- Cases where AI recommended but human ignored
"""
import json
import os
from collections import Counter, defaultdict

from human_trace_writer import load_traces


def analyze(entries):
    """Analyze a list of trace entries. Returns summary dict."""
    total = len(entries)
    if total == 0:
        return {"total": 0, "agree": 0, "disagree": 0, "agree_pct": 0.0}

    agree = sum(1 for e in entries if e.get("agree"))
    disagree = total - agree

    disagree_by_context = Counter()
    disagree_by_type = Counter()
    disagree_by_card = Counter()
    human_low_score = []
    ai_ignored = []

    for e in entries:
        if e.get("agree"):
            continue

        ctx = e.get("context", "")
        disagree_by_context[ctx] += 1

        options = e.get("options", [])
        ai_pick = set(e.get("ai_pick", []))
        human_pick = set(e.get("human_pick", []))

        for i in human_pick - ai_pick:
            opt = _get_option(options, i)
            if opt:
                disagree_by_type[opt.get("type", "")] += 1
                cid = opt.get("cardId")
                if cid:
                    name = opt.get("label", str(cid))
                    disagree_by_card[name] += 1
                score = opt.get("score", 0)
                ai_top_score = max((o.get("score", 0) for o in options), default=0)
                if ai_top_score > 0 and score < ai_top_score * 0.5:
                    human_low_score.append({
                        "turn": e.get("turn"),
                        "context": ctx,
                        "human_choice": opt.get("label", ""),
                        "human_score": score,
                        "ai_top_score": ai_top_score,
                        "gap": ai_top_score - score,
                    })

        for i in ai_pick - human_pick:
            opt = _get_option(options, i)
            if opt:
                ai_ignored.append({
                    "turn": e.get("turn"),
                    "context": ctx,
                    "ai_choice": opt.get("label", ""),
                    "ai_score": opt.get("score", 0),
                })

    return {
        "total": total,
        "agree": agree,
        "disagree": disagree,
        "agree_pct": round(100.0 * agree / total, 1) if total > 0 else 0.0,
        "disagree_by_context": dict(disagree_by_context.most_common(20)),
        "disagree_by_type": dict(disagree_by_type.most_common(20)),
        "disagree_by_card": dict(disagree_by_card.most_common(20)),
        "human_low_score_choices": human_low_score[:20],
        "ai_ignored_choices": ai_ignored[:20],
    }


def _get_option(options, index):
    for o in options:
        if o.get("i") == index:
            return o
    return None


def format_report(summary):
    """Format analysis summary as Markdown."""
    lines = ["# Human Trace Analysis\n"]
    lines.append("## Overview\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Total decisions | %d |" % summary.get("total", 0))
    lines.append("| Agree (human == AI) | %d |" % summary.get("agree", 0))
    lines.append("| Disagree | %d |" % summary.get("disagree", 0))
    lines.append("| Agreement rate | %.1f%% |" % summary.get("agree_pct", 0))

    by_ctx = summary.get("disagree_by_context", {})
    if by_ctx:
        lines.append("\n## Disagreements by Context\n")
        lines.append("| Context | Count |")
        lines.append("|---------|-------|")
        for ctx, count in sorted(by_ctx.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (ctx, count))

    by_card = summary.get("disagree_by_card", {})
    if by_card:
        lines.append("\n## Disagreements by Card\n")
        lines.append("| Card | Count |")
        lines.append("|------|-------|")
        for card, count in sorted(by_card.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (card, count))

    low = summary.get("human_low_score_choices", [])
    if low:
        lines.append("\n## Human chose low-score options\n")
        lines.append("| Turn | Context | Choice | Score | AI Top | Gap |")
        lines.append("|------|---------|--------|-------|--------|-----|")
        for item in low[:10]:
            lines.append("| %s | %s | %s | %.0f | %.0f | %.0f |" % (
                item.get("turn", ""), item.get("context", ""),
                item.get("human_choice", ""), item.get("human_score", 0),
                item.get("ai_top_score", 0), item.get("gap", 0)))

    ignored = summary.get("ai_ignored_choices", [])
    if ignored:
        lines.append("\n## AI recommended but human ignored\n")
        lines.append("| Turn | Context | AI Choice | AI Score |")
        lines.append("|------|---------|-----------|----------|")
        for item in ignored[:10]:
            lines.append("| %s | %s | %s | %.0f |" % (
                item.get("turn", ""), item.get("context", ""),
                item.get("ai_choice", ""), item.get("ai_score", 0)))

    return "\n".join(lines) + "\n"


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python human_trace_analyzer.py <trace.jsonl>")
        sys.exit(1)

    entries = load_traces(sys.argv[1])
    summary = analyze(entries)

    out_json = sys.argv[1].replace(".jsonl", "_analysis.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("Analysis saved to %s" % out_json)

    out_md = sys.argv[1].replace(".jsonl", "_analysis.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(format_report(summary))
    print("Report saved to %s" % out_md)


if __name__ == "__main__":
    main()
