"""Analyze human play traces vs AI recommendations.

Reads JSONL trace files and computes:
- Agreement rate (human == AI)
- Disagreements by option_type, card_id, context
- Strategy-tag disagreement buckets from the recording UI
- Cases where human chose low-AI-score options
- Cases where AI recommended but human ignored
- Improvement candidates for manual tuning
"""
import glob
import json
import os
from collections import Counter, defaultdict

try:
    from human_trace_writer import load_traces
except ImportError:  # package import from tests
    from experiments.web.human_trace_writer import load_traces


_STRATEGY_TAG_FIELDS = (
    ("turn_goal", "disagree_by_turn_goal"),
    ("win_plan_tags", "disagree_by_win_plan"),
    ("risk_flags", "disagree_by_risk"),
    ("human_reason_tags", "disagree_by_reason"),
)

_TAG_LABELS = {
    "setup_board": "盤面展開",
    "prepare_next_turn_attack": "次ターン攻撃準備",
    "take_ko_now": "今KO",
    "take_two_prizes": "サイド2枚取り",
    "close_game": "勝ち切り",
    "prevent_loss": "負け筋ケア",
    "improve_hand": "手札改善",
    "preserve_resources": "リソース温存",
    "disrupt_opponent": "相手妨害",
    "ko_active": "バトル場KO",
    "boss_two_prize_target": "ボスで2枚取り",
    "raging_bolt_big_damage_next_turn": "次ターン高火力",
    "ogerpon_energy_engine": "オーガポンエネ加速",
    "remove_main_attacker": "主力除去",
    "win_by_prize_race": "サイドレース勝ち",
    "win_by_resource": "リソース差勝ち",
    "win_by_deck_out_avoidance": "山切れ回避",
    "active_may_be_ko_next_turn": "次ターンKOリスク",
    "no_next_attacker": "次アタッカーなし",
    "not_enough_energy": "エネ不足",
    "low_hand": "手札弱い",
    "low_deck": "山札少ない",
    "boss_needed_for_win": "ボス温存",
    "bench_liability": "ベンチ負け筋",
    "behind_prize_race": "サイド遅れ",
    "build_raging_bolt_damage": "タケルライコ火力準備",
    "prioritize_energy_acceleration": "エネ加速優先",
    "avoid_bad_hand": "事故回避",
    "avoid_deck_out": "山切れ回避",
    "gust_win_condition": "ボス勝ち筋",
    "retreat_or_switch_safety": "入替安全",
    "other": "その他",
}

_HINTS = {
    "prepare_next_turn_attack": "次ターンの攻撃準備・エネ加速・アタッカー準備の将来価値が低く見積もられている可能性があります。",
    "take_ko_now": "即KOやサイド取得の評価が人間判断とずれている可能性があります。",
    "take_two_prizes": "2枚取り対象やボス系アクションの評価を確認するとよさそうです。",
    "close_game": "詰め局面の勝ち切り行動が弱い可能性があります。",
    "prevent_loss": "負け筋ケア、防御的な入替・ベンチ管理・リソース温存の評価を確認してください。",
    "improve_hand": "手札改善札の評価が低すぎる、または不要な場面で高すぎる可能性があります。",
    "preserve_resources": "リソース温存より短期スコアを優先しすぎている可能性があります。",
    "disrupt_opponent": "妨害札の使いどころが人間判断とずれている可能性があります。",
    "not_enough_energy": "エネ不足時のエネ加速・エネ回収・手貼り先評価を重点的に見るとよさそうです。",
    "low_hand": "手札が弱い場面でのドロー/サーチ優先度を確認してください。",
    "no_next_attacker": "次アタッカー準備の評価が足りない可能性があります。",
    "bench_liability": "ベンチ負け筋やサイド複数取りリスクの評価を見直す候補です。",
    "behind_prize_race": "サイドレースで遅れている時の攻撃的な選択が弱い可能性があります。",
    "prioritize_energy_acceleration": "エネ加速アクションのスコアや条件分岐を確認してください。",
    "build_raging_bolt_damage": "タケルライコの火力準備に関わるエネルギー枚数・回収・加速評価を確認してください。",
    "gust_win_condition": "ボス/呼び出しによる勝ち筋評価を確認してください。",
}


def analyze(entries):
    """Analyze a list of trace entries. Returns summary dict."""
    decisions = [e for e in entries if e.get("type", "decision") == "decision"]
    result_counts = Counter(e.get("result", "unknown") for e in entries if e.get("type") == "game_result")
    total = len(decisions)
    if total == 0:
        return _empty_summary(result_counts)

    agree = sum(1 for e in decisions if _picks_agree(e))
    disagree = total - agree

    disagree_by_context = Counter()
    disagree_by_type = Counter()
    disagree_by_card = Counter()
    tag_counts = {field: Counter() for field, _ in _STRATEGY_TAG_FIELDS}
    tag_disagree = {out_key: Counter() for _, out_key in _STRATEGY_TAG_FIELDS}
    tag_score_gap = defaultdict(list)
    human_low_score = []
    ai_ignored = []
    considered = {
        "with_considered": 0,
        "human_pick_in_considered": 0,
        "ai_pick_in_considered": 0,
        "human_pick_not_considered": 0,
    }

    for e in decisions:
        is_agree = _picks_agree(e)
        ctx = e.get("context", "")
        options = e.get("options", [])
        ai_pick = set(e.get("ai_pick", []))
        human_pick = set(e.get("human_pick", []))
        ai_top_score = max((o.get("score", 0) for o in options), default=0)

        for field, out_key in _STRATEGY_TAG_FIELDS:
            values = _tag_values(e, field)
            tag_counts[field].update(values)
            if not is_agree:
                tag_disagree[out_key].update(values)

        cons = set(i for i in e.get("human_considered", []) if isinstance(i, int))
        if cons:
            considered["with_considered"] += 1
            if human_pick & cons:
                considered["human_pick_in_considered"] += 1
            if ai_pick & cons:
                considered["ai_pick_in_considered"] += 1
            if human_pick and not (human_pick <= cons):
                considered["human_pick_not_considered"] += 1

        if is_agree:
            continue

        disagree_by_context[ctx] += 1

        for i in human_pick - ai_pick:
            opt = _get_option(options, i)
            if not opt:
                continue
            disagree_by_type[opt.get("type", "")] += 1
            cid = opt.get("cardId")
            if cid:
                name = opt.get("label", str(cid))
                disagree_by_card[name] += 1
            score = opt.get("score", 0)
            gap = ai_top_score - score
            _add_gap(tag_score_gap, e, gap)
            if ai_top_score > 0 and score < ai_top_score * 0.5:
                human_low_score.append({
                    "turn": e.get("turn"),
                    "context": ctx,
                    "turn_goal": e.get("turn_goal", ""),
                    "reason_tags": e.get("human_reason_tags", []),
                    "human_choice": opt.get("label", ""),
                    "human_score": score,
                    "ai_top_score": ai_top_score,
                    "gap": gap,
                })

        for i in ai_pick - human_pick:
            opt = _get_option(options, i)
            if opt:
                ai_ignored.append({
                    "turn": e.get("turn"),
                    "context": ctx,
                    "turn_goal": e.get("turn_goal", ""),
                    "reason_tags": e.get("human_reason_tags", []),
                    "ai_choice": opt.get("label", ""),
                    "ai_score": opt.get("score", 0),
                })

    tag_gap_summary = _summarize_tag_gaps(tag_score_gap)
    summary = {
        "total": total,
        "agree": agree,
        "disagree": disagree,
        "agree_pct": round(100.0 * agree / total, 1) if total > 0 else 0.0,
        "game_results": dict(result_counts),
        "disagree_by_context": dict(disagree_by_context.most_common(20)),
        "disagree_by_type": dict(disagree_by_type.most_common(20)),
        "disagree_by_card": dict(disagree_by_card.most_common(20)),
        "tag_counts": {k: dict(v.most_common(20)) for k, v in tag_counts.items()},
        "disagree_by_turn_goal": dict(tag_disagree["disagree_by_turn_goal"].most_common(20)),
        "disagree_by_win_plan": dict(tag_disagree["disagree_by_win_plan"].most_common(20)),
        "disagree_by_risk": dict(tag_disagree["disagree_by_risk"].most_common(20)),
        "disagree_by_reason": dict(tag_disagree["disagree_by_reason"].most_common(20)),
        "tag_score_gaps": tag_gap_summary,
        "considered_summary": considered,
        "human_low_score_choices": human_low_score[:20],
        "ai_ignored_choices": ai_ignored[:20],
    }
    summary["improvement_candidates"] = _build_improvement_candidates(summary)
    return summary


def _empty_summary(result_counts=None):
    return {
        "total": 0,
        "agree": 0,
        "disagree": 0,
        "agree_pct": 0.0,
        "game_results": dict(result_counts or {}),
        "disagree_by_context": {},
        "disagree_by_type": {},
        "disagree_by_card": {},
        "tag_counts": {},
        "disagree_by_turn_goal": {},
        "disagree_by_win_plan": {},
        "disagree_by_risk": {},
        "disagree_by_reason": {},
        "tag_score_gaps": {},
        "considered_summary": {
            "with_considered": 0,
            "human_pick_in_considered": 0,
            "ai_pick_in_considered": 0,
            "human_pick_not_considered": 0,
        },
        "human_low_score_choices": [],
        "ai_ignored_choices": [],
        "improvement_candidates": [],
    }


def _picks_agree(entry):
    if "agree" in entry:
        return bool(entry.get("agree"))
    ai_pick = entry.get("ai_pick", [])
    human_pick = entry.get("human_pick", [])
    return bool(ai_pick and human_pick and set(ai_pick) == set(human_pick))


def _tag_values(entry, field):
    value = entry.get(field)
    if not value:
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    if isinstance(value, str):
        return [value]
    return []


def _add_gap(tag_score_gap, entry, gap):
    if gap <= 0:
        return
    for field, _ in _STRATEGY_TAG_FIELDS:
        for tag in _tag_values(entry, field):
            tag_score_gap[tag].append(gap)


def _summarize_tag_gaps(tag_score_gap):
    out = {}
    for tag, gaps in tag_score_gap.items():
        if not gaps:
            continue
        out[tag] = {
            "count": len(gaps),
            "avg_gap": round(sum(gaps) / len(gaps), 1),
            "max_gap": max(gaps),
        }
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["avg_gap"]))[:20])


def _build_improvement_candidates(summary):
    candidates = []
    buckets = [
        ("turn_goal", summary.get("disagree_by_turn_goal", {})),
        ("risk", summary.get("disagree_by_risk", {})),
        ("reason", summary.get("disagree_by_reason", {})),
        ("win_plan", summary.get("disagree_by_win_plan", {})),
    ]
    tag_gaps = summary.get("tag_score_gaps", {})
    for field, counter in buckets:
        for tag, count in sorted(counter.items(), key=lambda x: -x[1])[:5]:
            gap_info = tag_gaps.get(tag, {})
            candidates.append({
                "kind": "strategy_tag",
                "field": field,
                "tag": tag,
                "label": _TAG_LABELS.get(tag, tag),
                "disagreements": count,
                "avg_score_gap": gap_info.get("avg_gap", 0),
                "suggestion": _HINTS.get(tag, "このタグが付いた局面でAI推奨と人間選択のズレが多いです。関連する評価値や条件分岐を確認してください。"),
            })
    for card, count in list(summary.get("disagree_by_card", {}).items())[:5]:
        candidates.append({
            "kind": "option_label",
            "field": "card_or_action",
            "tag": card,
            "label": card,
            "disagreements": count,
            "avg_score_gap": 0,
            "suggestion": "このカード/行動でズレが多いです。params_recommender.py の提案と合わせて評価値を確認してください。",
        })
    return sorted(candidates, key=lambda x: (-x.get("disagreements", 0), -x.get("avg_score_gap", 0)))[:20]


def _get_option(options, index):
    for o in options:
        if o.get("i") == index:
            return o
    return None


def _md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


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

    results = summary.get("game_results", {})
    if results:
        lines.append("\n## Game Results\n")
        lines.append("| Result | Count |")
        lines.append("|--------|-------|")
        for result, count in sorted(results.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (_md(result), count))

    by_ctx = summary.get("disagree_by_context", {})
    if by_ctx:
        lines.append("\n## Disagreements by Context\n")
        lines.append("| Context | Count |")
        lines.append("|---------|-------|")
        for ctx, count in sorted(by_ctx.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (_md(ctx), count))

    _append_counter_section(lines, "Disagreements by Turn Goal", summary.get("disagree_by_turn_goal", {}))
    _append_counter_section(lines, "Disagreements by Human Reason", summary.get("disagree_by_reason", {}))
    _append_counter_section(lines, "Disagreements by Risk", summary.get("disagree_by_risk", {}))
    _append_counter_section(lines, "Disagreements by Win Plan", summary.get("disagree_by_win_plan", {}))

    considered = summary.get("considered_summary", {})
    if considered and considered.get("with_considered", 0):
        lines.append("\n## Considered Option Coverage\n")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append("| Decisions with considered options | %d |" % considered.get("with_considered", 0))
        lines.append("| Human pick was considered | %d |" % considered.get("human_pick_in_considered", 0))
        lines.append("| AI pick was considered | %d |" % considered.get("ai_pick_in_considered", 0))
        lines.append("| Human pick was not checked as considered | %d |" % considered.get("human_pick_not_considered", 0))

    candidates = summary.get("improvement_candidates", [])
    if candidates:
        lines.append("\n## Improvement Candidates\n")
        lines.append("| Kind | Label | Disagreements | Avg Gap | Suggestion |")
        lines.append("|------|-------|---------------|---------|------------|")
        for item in candidates[:10]:
            lines.append("| %s | %s | %d | %.1f | %s |" % (
                _md(item.get("field", item.get("kind", ""))),
                _md(item.get("label", item.get("tag", ""))),
                item.get("disagreements", 0),
                item.get("avg_score_gap", 0),
                _md(item.get("suggestion", "")),
            ))

    by_card = summary.get("disagree_by_card", {})
    if by_card:
        lines.append("\n## Disagreements by Card / Action\n")
        lines.append("| Card / Action | Count |")
        lines.append("|---------------|-------|")
        for card, count in sorted(by_card.items(), key=lambda x: -x[1]):
            lines.append("| %s | %d |" % (_md(card), count))

    low = summary.get("human_low_score_choices", [])
    if low:
        lines.append("\n## Human chose low-score options\n")
        lines.append("| Turn | Context | Goal | Choice | Score | AI Top | Gap |")
        lines.append("|------|---------|------|--------|-------|--------|-----|")
        for item in low[:10]:
            lines.append("| %s | %s | %s | %s | %.0f | %.0f | %.0f |" % (
                item.get("turn", ""), _md(item.get("context", "")),
                _md(_TAG_LABELS.get(item.get("turn_goal", ""), item.get("turn_goal", ""))),
                _md(item.get("human_choice", "")), item.get("human_score", 0),
                item.get("ai_top_score", 0), item.get("gap", 0)))

    ignored = summary.get("ai_ignored_choices", [])
    if ignored:
        lines.append("\n## AI recommended but human ignored\n")
        lines.append("| Turn | Context | Goal | AI Choice | AI Score |")
        lines.append("|------|---------|------|-----------|----------|")
        for item in ignored[:10]:
            lines.append("| %s | %s | %s | %s | %.0f |" % (
                item.get("turn", ""), _md(item.get("context", "")),
                _md(_TAG_LABELS.get(item.get("turn_goal", ""), item.get("turn_goal", ""))),
                _md(item.get("ai_choice", "")), item.get("ai_score", 0)))

    return "\n".join(lines) + "\n"


def _append_counter_section(lines, title, counter):
    if not counter:
        return
    lines.append("\n## %s\n" % title)
    lines.append("| Tag | Label | Count |")
    lines.append("|-----|-------|-------|")
    for tag, count in sorted(counter.items(), key=lambda x: -x[1]):
        lines.append("| %s | %s | %d |" % (_md(tag), _md(_TAG_LABELS.get(tag, tag)), count))


def load_trace_inputs(paths):
    """Load trace entries from one or more JSONL files or directories."""
    entries = []
    loaded_files = []
    for path in paths:
        if os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "*.jsonl")))
        else:
            files = sorted(glob.glob(path)) or [path]
        for file_path in files:
            if not file_path.endswith(".jsonl"):
                continue
            loaded = load_traces(file_path)
            if loaded:
                loaded_files.append(file_path)
                entries.extend(loaded)
    return entries, loaded_files


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python human_trace_analyzer.py <trace.jsonl|trace_dir> [more traces...]")
        sys.exit(1)

    entries, loaded_files = load_trace_inputs(sys.argv[1:])
    summary = analyze(entries)
    summary["source_files"] = loaded_files

    if len(loaded_files) == 1:
        out_json = loaded_files[0].replace(".jsonl", "_analysis.json")
        out_md = loaded_files[0].replace(".jsonl", "_analysis.md")
    else:
        out_json = "human_trace_analysis.json"
        out_md = "human_trace_analysis.md"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("Analysis saved to %s" % out_json)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(format_report(summary))
    print("Report saved to %s" % out_md)
    print("Loaded files: %d" % len(loaded_files))
    print("Decisions analyzed: %d" % summary.get("total", 0))
    print("Agreement: %.1f%%" % summary.get("agree_pct", 0.0))


if __name__ == "__main__":
    main()
