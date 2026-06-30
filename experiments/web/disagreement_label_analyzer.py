"""Aggregate human-filled disagreement_labels.jsonl into a review summary.

This does NOT train anything. It turns human review labels (human_better /
agent_better / both_ok / both_bad / unclear) into counts and candidate
main.py / params.json targets, and reports how many high-confidence labels
are ready to feed into a future action-value-learning step.

Usage:
    python experiments/web/disagreement_label_analyzer.py \
        --labels experiments/web/disagreement_labels.jsonl \
        --items experiments/web/disagreement_review_items.json
"""
import argparse
import json
import os

VALID_LABELS = {"human_better", "agent_better", "both_ok", "both_bad", "unclear"}
VALID_CONFIDENCES = {"high", "medium", "low"}

DEFAULT_LABELS_JSONL = "experiments/web/disagreement_labels.jsonl"
DEFAULT_ITEMS_JSON = "experiments/web/disagreement_review_items.json"
DEFAULT_SUMMARY_JSON = "experiments/web/disagreement_label_summary.json"
DEFAULT_SUMMARY_MD = "experiments/web/disagreement_label_summary.md"

_RECOMMENDATION_RULES = {
    "attack_too_early": {
        "target": "ATTACK cap / _score_attack",
        "param_candidates": ["search_weight_immediate", "impact_bt_ko_prize_mult"],
        "suggestion": "PLAY/ABILITY が残っている場面で攻撃スコアが高すぎる可能性。cap を下げるか、サポーター未使用時のペナルティを追加検討",
    },
    "opponent_return_ko_underestimated": {
        "target": "eval_active_ko_risk / _estimate_opp_damage",
        "param_candidates": ["eval_active_ko_risk", "eval_no_backup_risk"],
        "suggestion": "返り討ちリスクの評価を強めるか、_estimate_opp_damage の閾値見直しを検討",
    },
    "no_next_attacker": {
        "target": "eval_no_backup_risk / _detect_strategy",
        "param_candidates": ["eval_no_backup_risk", "impact_play_bolt"],
        "suggestion": "次アタッカー不在リスクの評価を強めるか、ベンチ展開の優先度を上げる",
    },
    "boss_used_too_early": {
        "target": "_score_boss / win_condition",
        "param_candidates": ["impact_boss", "eval_boss_timing"],
        "suggestion": "Boss's Orders を早期に使いすぎている。サイド枚数条件など使用タイミングの見直しを検討",
    },
    "boss_missed": {
        "target": "_score_boss / win_condition",
        "param_candidates": ["impact_boss", "eval_boss_timing"],
        "suggestion": "Boss's Orders を使うべき場面で使っていない。ex 狙いの検出ロジックを見直し",
    },
    "setup_too_slow": {
        "target": "_score_play_pokemon / turn_plan",
        "param_candidates": ["impact_play_bolt", "impact_play_ogerpon"],
        "suggestion": "展開速度が遅い。場の展開を優先するスコアリングを検討",
    },
    "end_turn_bad": {
        "target": "_score_end_turn",
        "param_candidates": ["eval_end_turn_penalty"],
        "suggestion": "ターン終了の選択が悪い場面が多い。終了前にできる行動の評価を見直し",
    },
    "hand_refresh_overvalued": {
        "target": "_score_hand_refresh",
        "param_candidates": ["impact_hand_refresh"],
        "suggestion": "手札リフレッシュ系の評価が過大。優先度を下げる検討",
    },
    "agreement_bad_risk": {
        "target": "risk evaluation (shared by AI and human)",
        "param_candidates": ["eval_active_ko_risk", "eval_no_backup_risk"],
        "suggestion": "AIと人間が同じ選択をして負けた場面。リスク評価そのものが甘い可能性",
    },
}


def load_labels(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def load_items(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _count_by(counter, key):
    if key is None:
        return
    counter[key] = counter.get(key, 0) + 1


def _nested_count(nested, outer_key, inner_key):
    if outer_key is None or inner_key is None:
        return
    bucket = nested.setdefault(outer_key, {})
    bucket[inner_key] = bucket.get(inner_key, 0) + 1


def analyze(labels, items, warn=print):
    items_by_id = {it["review_id"]: it for it in items}

    label_counts = {}
    invalid_label_count = 0
    invalid_confidence_count = 0
    category_label = {}
    action_type_label = {}
    card_label = {}
    high_confidence_labeled = 0
    total_labeled = 0

    dominant = {"human_better": [], "agent_better": [], "both_bad": [], "unclear": []}

    for rec in labels:
        label = rec.get("label", "") or ""
        confidence = rec.get("confidence", "") or ""

        if label and label not in VALID_LABELS:
            warn("[warn] invalid label %r for review_id=%s, skipping from counts" %
                 (label, rec.get("review_id")))
            invalid_label_count += 1
            continue
        if confidence and confidence not in VALID_CONFIDENCES:
            warn("[warn] invalid confidence %r for review_id=%s" %
                 (confidence, rec.get("review_id")))
            invalid_confidence_count += 1
            confidence = ""

        key = label if label else "unlabeled"
        _count_by(label_counts, key)

        if not label:
            continue
        total_labeled += 1
        if confidence == "high":
            high_confidence_labeled += 1

        item = items_by_id.get(rec.get("review_id"))
        category = rec.get("category") or (item.get("category") if item else None)
        action_type = item.get("human_action_type") if item else None
        card = (item.get("human_action") or item.get("ai_action")) if item else (
            rec.get("human_action") or rec.get("ai_action"))

        _nested_count(category_label, category, label)
        _nested_count(action_type_label, action_type, label)
        _nested_count(card_label, card, label)

        if label in dominant:
            dominant[label].append(rec.get("review_id"))

    recommendations = []
    for category, labels_for_cat in category_label.items():
        if category in _RECOMMENDATION_RULES and labels_for_cat.get("human_better", 0) >= 2:
            rule = _RECOMMENDATION_RULES[category]
            recommendations.append({
                "category": category,
                "human_better_count": labels_for_cat["human_better"],
                "target": rule["target"],
                "param_candidates": rule["param_candidates"],
                "suggestion": rule["suggestion"],
            })
    recommendations.sort(key=lambda r: -r["human_better_count"])

    return {
        "label_counts": label_counts,
        "invalid_label_count": invalid_label_count,
        "invalid_confidence_count": invalid_confidence_count,
        "total_labeled": total_labeled,
        "total_records": len(labels),
        "high_confidence_labeled": high_confidence_labeled,
        "category_label_distribution": category_label,
        "action_type_label_distribution": action_type_label,
        "card_label_distribution": card_label,
        "dominant_human_better": dominant["human_better"],
        "dominant_agent_better": dominant["agent_better"],
        "dominant_both_bad": dominant["both_bad"],
        "dominant_unclear": dominant["unclear"],
        "recommendations": recommendations,
    }


def _dist_table(lines, title, dist):
    lines.append("\n## %s\n" % title)
    if not dist:
        lines.append("(none)\n")
        return
    all_labels = sorted({l for v in dist.values() for l in v})
    lines.append("| Key | " + " | ".join(all_labels) + " |")
    lines.append("|-----|" + "|".join(["---"] * len(all_labels)) + "|")
    for key, counts in dist.items():
        row = [str(counts.get(l, 0)) for l in all_labels]
        lines.append("| %s | %s |" % (key, " | ".join(row)))


def format_report(summary):
    lines = ["# Disagreement Label Summary\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append("| Total label records | %d |" % summary["total_records"])
    lines.append("| Labeled | %d |" % summary["total_labeled"])
    lines.append("| High-confidence labeled | %d |" % summary["high_confidence_labeled"])
    lines.append("| Invalid label values (skipped) | %d |" % summary["invalid_label_count"])
    lines.append("| Invalid confidence values | %d |" % summary["invalid_confidence_count"])

    lines.append("\n## Label Counts\n")
    lines.append("| Label | Count |")
    lines.append("|-------|-------|")
    for label, cnt in sorted(summary["label_counts"].items(), key=lambda kv: -kv[1]):
        lines.append("| %s | %d |" % (label, cnt))

    _dist_table(lines, "Category x Label", summary["category_label_distribution"])
    _dist_table(lines, "Action Type x Label", summary["action_type_label_distribution"])
    _dist_table(lines, "Card/Action x Label", summary["card_label_distribution"])

    for title, key in [
        ("Scenes Where Human Was Better", "dominant_human_better"),
        ("Scenes Where Agent Was Better", "dominant_agent_better"),
        ("Scenes Both Were Bad", "dominant_both_bad"),
        ("Scenes Unclear", "dominant_unclear"),
    ]:
        lines.append("\n## %s\n" % title)
        ids = summary[key]
        if not ids:
            lines.append("(none)\n")
        else:
            for rid in ids:
                lines.append("- %s" % rid)

    lines.append("\n## Candidate main.py / params.json Fixes\n")
    if not summary["recommendations"]:
        lines.append("(no category currently has >=2 human_better confirmations)\n")
    else:
        for rec in summary["recommendations"]:
            lines.append("- **%s** (human_better x%d): %s — params: %s" % (
                rec["target"], rec["human_better_count"], rec["suggestion"],
                ", ".join(rec["param_candidates"])))

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=DEFAULT_LABELS_JSONL)
    parser.add_argument("--items", default=DEFAULT_ITEMS_JSON)
    parser.add_argument("--output-json", default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--output-md", default=DEFAULT_SUMMARY_MD)
    args = parser.parse_args()

    labels = load_labels(args.labels)
    items = load_items(args.items)
    summary = analyze(labels, items)

    os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    os.makedirs(os.path.dirname(args.output_md) or ".", exist_ok=True)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(format_report(summary))

    print("Labeled %d/%d (%d high-confidence) -> %s, %s" % (
        summary["total_labeled"], summary["total_records"],
        summary["high_confidence_labeled"], args.output_json, args.output_md))


if __name__ == "__main__":
    main()
