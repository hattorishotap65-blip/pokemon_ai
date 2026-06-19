"""
Analyze deck.csv + card_knowledge.csv and write data/deck_profile.json.

Usage:
    python agent/deck_analyzer.py
    python agent/deck_analyzer.py --deck path/to/deck.csv --out data/deck_profile.json

The generated deck_profile.json is included in submission.tar.gz and loaded
at runtime by PolicyAgent to drive advantage weighting and win-condition tracking.
"""
import argparse
import json
import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)

from agent.card_knowledge import CardKnowledge
from agent.deck_evaluator  import evaluate as _evaluate_deck
from agent.concept_weights import WEIGHTS as _ARCH_WEIGHTS


# ---------------------------------------------------------------------------
# Defaults / paths
# ---------------------------------------------------------------------------

_DECK_PATH    = os.path.join(_ROOT, "deck.csv")
_MASTER_PATH  = os.path.join(_ROOT, "data", "card_master.csv")
_OUT_PATH     = os.path.join(_ROOT, "data", "deck_profile.json")


# ---------------------------------------------------------------------------
# Archetype scoring
# ---------------------------------------------------------------------------

def _score_archetypes(stats: dict) -> dict[str, float]:
    s = stats

    def _f(key, default=0.0):
        return float(s.get(key, default) or 0)

    has_evo = s.get("has_evolution", False)

    scores = {
        # Aggro: basic attackers, heavy energy, attack fast, penalise evolution
        "aggro": (
            _f("attacker_ratio") * 22.0
            + _f("energy_ratio") * 10.0
            + _f("avg_tempo_adv") * 1.2
            - (4.0 if has_evo else 0.0)
        ),
        # Setup midrange: evolution line is the key signal
        "setup_midrange": (
            (12.0 if has_evo else 0.0)
            + _f("search_ratio")  * 18.0
            + _f("draw_ratio")    * 12.0
            + _f("attacker_ratio") * 10.0
            + _f("energy_ratio")  * 6.0
            + (5.0 if has_evo and _f("attacker_ratio") > 0.05 else 0.0)
        ),
        # Combo: high search + card_adv, assembly-dependent
        "combo": (
            _f("search_ratio")      * 18.0
            + _f("avg_card_adv")    * 2.0
            + _f("combo_tag_ratio") * 10.0
            + _f("draw_ratio")      * 8.0
        ),
        # Control: disruption-heavy, resource preservation
        "control": (
            _f("disruption_ratio")         * 22.0
            + _f("recovery_ratio")         * 12.0
            + _f("avg_risk_reduction_adv") * 1.2
        ),
        # Resource loop: specifically needs MANY recovery cards (>10% of deck)
        "resource_loop": (
            _f("recovery_ratio") * 35.0
            + _f("avg_resource_adv") * 0.8
        ),
        # Prize race: high-value targets, gust effects
        "prize_race": (
            _f("attacker_ratio")  * 20.0
            + _f("disruption_ratio") * 8.0
            + _f("avg_prize_adv") * 2.0
        ),
    }
    return scores


def _pick_archetype(scores: dict[str, float]) -> tuple[str, float]:
    """Return (best_archetype, confidence_score 0-1)."""
    if not scores:
        return "setup_midrange", 0.3
    top = sorted(scores.items(), key=lambda x: -x[1])
    best_name, best_val = top[0]
    second_val = top[1][1] if len(top) > 1 else 0.0
    # Confidence: how clearly the best separates from second
    gap        = max(0.0, best_val - second_val)
    confidence = min(gap / max(best_val, 1.0), 1.0)
    return best_name, round(confidence, 2)


# ---------------------------------------------------------------------------
# Win-condition templates by archetype
# ---------------------------------------------------------------------------

_WIN_CONDITIONS = {
    "aggro": {
        "primary":   "Attach energy early and attack to take prizes quickly",
        "sub":       ["Attach energy turn 1-2", "Start attacking by turn 2-3",
                      "Close out with finisher before opponent stabilises"],
    },
    "setup_midrange": {
        "primary":   "Set up main attacker and win the mid-game prize race",
        "sub":       ["Expand bench in early game", "Evolve/ready main attacker by mid game",
                      "Maintain attack continuity and take final prizes in late game"],
    },
    "combo": {
        "primary":   "Assemble key pieces and execute the main combo for KOs",
        "sub":       ["Search out combo pieces", "Protect key cards until combo is ready",
                      "Execute combo and snowball prize lead"],
    },
    "control": {
        "primary":   "Disrupt opponent and grind out a resource advantage",
        "sub":       ["Disrupt opponent hand/board", "Preserve key resources",
                      "Win attrition when opponent runs out of options"],
    },
    "resource_loop": {
        "primary":   "Loop resources to sustain attacks and outlast opponent",
        "sub":       ["Recover energy and attackers from discard",
                      "Sustain attack chain across multiple turns",
                      "Win by resource advantage in late game"],
    },
    "prize_race": {
        "primary":   "Win the prize race through high-value KOs",
        "sub":       ["Target high-prize pokemon (ex/mega)",
                      "Use gust effects to access prize targets",
                      "Close out with finisher when ahead on prizes"],
    },
}


# ---------------------------------------------------------------------------
# Phase priorities by archetype
# ---------------------------------------------------------------------------

_PRIORITIES = {
    "aggro": {
        "early": ["attach_energy", "find_basic_pokemon", "setup_bench"],
        "mid":   ["start_attacking", "take_prizes", "maintain_energy"],
        "late":  ["take_final_prizes", "preserve_attacker"],
    },
    "setup_midrange": {
        "early": ["find_basic_pokemon", "setup_bench", "attach_energy", "draw_cards"],
        "mid":   ["evolve_main_attacker", "start_attacking", "maintain_energy", "take_prizes"],
        "late":  ["take_final_prizes", "avoid_deck_out", "preserve_key_resources"],
    },
    "combo": {
        "early": ["find_combo_pieces", "draw_cards", "protect_key_cards"],
        "mid":   ["assemble_combo", "maintain_hand", "start_attacking"],
        "late":  ["execute_combo", "take_final_prizes", "avoid_disruption"],
    },
    "control": {
        "early": ["disrupt_opponent", "draw_cards", "setup_defence"],
        "mid":   ["maintain_disruption", "recover_resources", "take_prizes_carefully"],
        "late":  ["close_out_on_resources", "preserve_key_cards", "avoid_deck_out"],
    },
    "resource_loop": {
        "early": ["setup_recovery_engine", "attach_energy", "draw_cards"],
        "mid":   ["loop_resources", "maintain_attack", "preserve_energy"],
        "late":  ["sustain_loop", "take_final_prizes", "avoid_deck_out"],
    },
    "prize_race": {
        "early": ["find_attackers", "attach_energy", "identify_prize_targets"],
        "mid":   ["target_high_prize_pokemon", "use_gust_effects", "maintain_attacker"],
        "late":  ["take_final_prizes", "use_finisher", "deny_opponent_recovery"],
    },
}


# ---------------------------------------------------------------------------
# Advantage weights per archetype (from concept_weights, pulled for profile)
# ---------------------------------------------------------------------------

def _advantage_weights_for_profile(archetype: str) -> dict:
    arch = _ARCH_WEIGHTS.get(archetype, {})
    result = {}
    for phase in ("early", "mid", "late"):
        phase_w = arch.get(phase, {})
        result[phase] = {
            k: round(phase_w.get(k, 1.0), 2)
            for k in ("card_adv", "board_adv", "energy_adv", "tempo_adv",
                      "prize_adv", "resource_adv", "info_adv", "risk_reduction_adv")
        }
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze(deck_path: str = None, out_path: str = None) -> dict:
    """
    Read deck.csv, compute stats, infer archetype, write deck_profile.json.
    Returns the profile dict.
    """
    deck_path = deck_path or _DECK_PATH
    out_path  = out_path  or _OUT_PATH

    # Load deck
    card_ids: list[int] = []
    try:
        with open(deck_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        card_ids.append(int(line))
                    except ValueError:
                        pass
    except FileNotFoundError:
        print(f"[deck_analyzer] deck not found: {deck_path}")
        return {}

    # Load knowledge
    knowledge = CardKnowledge()

    # Evaluate deck
    stats = _evaluate_deck(card_ids, knowledge)

    # Score archetypes
    arch_scores   = _score_archetypes(stats)
    archetype, conf = _pick_archetype(arch_scores)

    human_review  = conf < 0.5

    wc = _WIN_CONDITIONS.get(archetype, _WIN_CONDITIONS["setup_midrange"])
    pr = _PRIORITIES.get(archetype, _PRIORITIES["setup_midrange"])

    deck_name = os.path.splitext(os.path.basename(deck_path))[0]

    profile = {
        "deck_id":                deck_name,
        "archetype":              archetype,
        "confidence_score":       conf,
        "human_review_required":  human_review,
        "archetype_scores":       {k: round(v, 1) for k, v in
                                   sorted(arch_scores.items(), key=lambda x: -x[1])},
        "primary_win_condition":  wc["primary"],
        "sub_win_conditions":     wc["sub"],
        "main_attackers":         stats.get("main_attackers", []),
        "sub_attackers":          stats.get("sub_attackers", []),
        "setup_cards":            stats.get("setup_cards", []),
        "draw_engine":            stats.get("draw_engine", []),
        "search_engine":          stats.get("search_engine", []),
        "energy_engine":          stats.get("energy_engine", []),
        "disruption_cards":       stats.get("disruption_cards", []),
        "recovery_cards":         stats.get("recovery_cards", []),
        "weak_points":            _infer_weak_points(stats),
        "early_priorities":       pr["early"],
        "mid_priorities":         pr["mid"],
        "late_priorities":        pr["late"],
        "advantage_weights":      _advantage_weights_for_profile(archetype),
        "_deck_stats":            {
            "total_cards":             len(card_ids),
            "energy_ratio":            stats.get("energy_ratio"),
            "attacker_ratio":          stats.get("attacker_ratio"),
            "search_ratio":            stats.get("search_ratio"),
            "disruption_ratio":        stats.get("disruption_ratio"),
            "avg_tempo_adv":           stats.get("avg_tempo_adv"),
            "avg_prize_adv":           stats.get("avg_prize_adv"),
            "main_attacker_access":    stats.get("main_attacker_access_score"),
            "energy_consistency":      stats.get("energy_consistency_score"),
            "dead_card_rate":          stats.get("dead_card_rate"),
        },
    }

    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"[deck_analyzer] {archetype} (conf={conf}) -> {out_path}")
        if human_review:
            print("[deck_analyzer] confidence < 0.5: human_review_required=true")
    except OSError as e:
        print(f"[deck_analyzer] could not write {out_path}: {e}")

    return profile


def _infer_weak_points(stats: dict) -> list:
    weak = []
    if stats.get("dead_card_rate", 0) > 0.15:
        weak.append("high_dead_card_rate")
    if stats.get("main_attacker_access_score", 1) < 0.5:
        weak.append("low_main_attacker_access")
    if stats.get("energy_consistency_score", 1) < 0.6:
        weak.append("energy_inconsistency")
    if stats.get("recovery_ratio", 0) < 0.03:
        weak.append("low_recovery")
    if stats.get("disruption_ratio", 0) < 0.05:
        weak.append("low_disruption")
    if stats.get("draw_ratio", 0) < 0.05:
        weak.append("low_draw")
    return weak


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze deck and generate deck_profile.json")
    parser.add_argument("--deck", default=None)
    parser.add_argument("--out",  default=None)
    args = parser.parse_args()
    analyze(args.deck, args.out)
