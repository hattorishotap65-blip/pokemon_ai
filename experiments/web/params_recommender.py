"""Generate params.json correction recommendations from human trace analysis.

Reads human_trace_analyzer output and suggests param adjustments
based on systematic disagreements between human and AI.
"""
import json
import os
import sys

from human_trace_analyzer import analyze
from human_trace_writer import load_traces

_LABEL_TO_PARAM = {
    "Raging Bolt ex": "score_play_pokemon_raging_bolt",
    "Teal Mask Ogerpon ex": "score_play_pokemon_ogerpon",
    "Bellowing Thunder": "score_attack_bellowing_thunder",
    "Myriad Leaf Shower": "score_attack_myriad_leaf_shower",
    "Burst Roar": "score_attack_burst_roar",
    "Teal Dance": "score_ability_teal_dance",
    "Crispin": "score_supporter_crispin",
    "Lillie's Determination": "score_supporter_lillie",
    "Boss's Orders": "score_supporter_boss",
    "Ultra Ball": "score_item_ultra_ball",
    "Pokégear 3.0": "score_item_pokegear",
    "Bug Catching Set": "score_item_bug_catching_set",
    "Tera Orb": "score_item_tera_orb",
    "Energy Retrieval": "score_item_energy_retrieval",
    "Pokémon Catcher": "score_item_pokemon_catcher",
    "Unfair Stamp": "score_item_unfair_stamp",
}

_STEP = 20


def _match_param(label):
    """Try to match an option label to a params.json key."""
    for keyword, param in _LABEL_TO_PARAM.items():
        if keyword in label:
            return param
    if "エネルギーをつける" in label or "貼能量" in label:
        if "Ogerpon" in label:
            return "score_attach_energy_ogerpon_active"
        if "Raging Bolt" in label:
            return "score_attach_energy_raging_bolt_active"
        return "score_attach_energy_other"
    if "ターン終了" in label or "End Turn" in label:
        return "score_end_turn"
    if "にげる" in label or "Retreat" in label:
        return "score_retreat"
    return None


def recommend(entries, current_params=None):
    """Generate param adjustment recommendations.

    Returns:
        dict with 'adjustments' (param -> delta) and 'details' (explanations)
    """
    if current_params is None:
        current_params = {}

    summary = analyze(entries)
    adjustments = {}
    details = []

    # Human chose options the AI scored low -> increase those params
    for item in summary.get("human_low_score_choices", []):
        label = item.get("human_choice", "")
        param = _match_param(label)
        if param:
            gap = item.get("gap", 0)
            delta = min(int(gap * 0.3), 100)
            delta = max(delta, _STEP)
            if param in adjustments:
                adjustments[param] = max(adjustments[param], delta)
            else:
                adjustments[param] = delta
            details.append({
                "param": param,
                "direction": "increase",
                "delta": delta,
                "reason": "Human chose '%s' (score=%.0f) over AI top (score=%.0f)" % (
                    label, item.get("human_score", 0), item.get("ai_top_score", 0)),
            })

    # AI recommended but human ignored -> decrease those params
    for item in summary.get("ai_ignored_choices", []):
        label = item.get("ai_choice", "")
        param = _match_param(label)
        if param:
            delta = -_STEP
            if param in adjustments:
                adjustments[param] = min(adjustments[param], delta)
            else:
                adjustments[param] = delta
            details.append({
                "param": param,
                "direction": "decrease",
                "delta": delta,
                "reason": "AI recommended '%s' (score=%.0f) but human ignored" % (
                    label, item.get("ai_score", 0)),
            })

    # Compute proposed values
    proposed = {}
    for param, delta in adjustments.items():
        current = current_params.get(param, 500)
        proposed[param] = current + delta

    return {
        "adjustments": adjustments,
        "proposed": proposed,
        "details": details,
        "summary": {
            "total_decisions": summary.get("total", 0),
            "agreement_pct": summary.get("agree_pct", 0),
            "params_to_adjust": len(adjustments),
        },
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python params_recommender.py <trace.jsonl> [params.json]")
        sys.exit(1)

    trace_path = sys.argv[1]
    entries = load_traces(trace_path)

    current_params = {}
    if len(sys.argv) >= 3:
        with open(sys.argv[2], encoding="utf-8") as f:
            current_params = json.load(f)

    result = recommend(entries, current_params)

    out_dir = os.path.dirname(trace_path) or "."
    out_path = os.path.join(out_dir, "params_recommendations.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("Recommendations saved to %s" % out_path)
    print("  Decisions analyzed: %d" % result["summary"]["total_decisions"])
    print("  Agreement: %.1f%%" % result["summary"]["agreement_pct"])
    print("  Params to adjust: %d" % result["summary"]["params_to_adjust"])

    if result["adjustments"]:
        print("\nProposed adjustments:")
        for param, delta in sorted(result["adjustments"].items()):
            sign = "+" if delta > 0 else ""
            print("  %s: %s%d" % (param, sign, delta))


if __name__ == "__main__":
    main()
