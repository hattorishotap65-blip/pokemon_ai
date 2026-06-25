"""
Feature extraction for candidate decks.

Converts a deck (list of card IDs) into a flat feature dict suitable
for ML models or surrogate scoring. No ML model is trained here —
this module only produces the feature vectors.
"""
from __future__ import annotations
import json
from collections import Counter
from typing import Dict, List

from experiments.deck_search.cards import CardInfo, card_db, BASIC_ENERGY_IDS

_DRAW_TRAINER_IDS = {1192, 1227, 1235, 1212, 1213, 1224, 1225, 1229}
_SEARCH_TRAINER_IDS = {1086, 1097, 1102, 1121, 1115, 1122}
_SWITCH_IDS = {1123, 1129}
_GUST_IDS = {1182, 1184}
_STADIUM_IDS = {1252, 1255, 1256, 1260, 1264, 1266}
_TOOL_IDS = {1159, 1156, 1161, 1171, 1174}
_DISRUPTION_IDS = {1120, 1145, 1146}


def extract_features(card_ids: List[int]) -> Dict[str, float]:
    """Extract ML-ready features from a deck list."""
    db = card_db()
    counts = Counter(card_ids)

    total = len(card_ids)
    pokemon = energy = trainer = 0
    basic_pokemon = stage1 = stage2 = 0
    ex_count = mega_ex_count = ace_spec = 0
    total_hp = 0
    total_retreat = 0

    draw_support = search = switch = gust = stadium = tool = disruption = 0

    energy_type_counts: Dict[int, int] = Counter()
    unique_pokemon: set = set()

    for cid, cnt in counts.items():
        card = db.get(cid)
        if card is None:
            continue

        if card.is_pokemon:
            pokemon += cnt
            unique_pokemon.add(cid)
            total_hp += card.hp * cnt
            total_retreat += card.retreat_cost * cnt
            if card.is_basic:
                basic_pokemon += cnt
            if card.is_stage1:
                stage1 += cnt
            if card.is_stage2:
                stage2 += cnt
            if card.is_ex:
                ex_count += cnt
            if card.is_mega_ex:
                mega_ex_count += cnt
        elif card.is_energy:
            energy += cnt
            energy_type_counts[cid] += cnt
        elif card.is_trainer:
            trainer += cnt

        if card.is_ace_spec:
            ace_spec += cnt
        if cid in _DRAW_TRAINER_IDS:
            draw_support += cnt
        if cid in _SEARCH_TRAINER_IDS:
            search += cnt
        if cid in _SWITCH_IDS:
            switch += cnt
        if cid in _GUST_IDS:
            gust += cnt
        if cid in _STADIUM_IDS:
            stadium += cnt
        if cid in _TOOL_IDS:
            tool += cnt
        if cid in _DISRUPTION_IDS:
            disruption += cnt

    dominant_energy = max(energy_type_counts.values()) if energy_type_counts else 0
    energy_diversity = len(energy_type_counts)

    main_attacker = ex_count + mega_ex_count
    secondary_attacker = max(0, pokemon - basic_pokemon - main_attacker)

    consistency = min(10.0, (
        draw_support * 0.8 +
        search * 1.0 +
        min(basic_pokemon, 8) * 0.5 +
        (1.0 if energy >= 10 else 0.0) +
        (1.0 if dominant_energy >= 8 else 0.0)
    ))

    attack_readiness = min(10.0, (
        main_attacker * 1.5 +
        (1.0 if basic_pokemon >= 4 else 0.0) +
        (energy / 6.0) +
        switch * 0.3
    ))

    counterplay = min(10.0, (
        gust * 1.5 +
        disruption * 0.8 +
        switch * 0.5 +
        (1.0 if ace_spec else 0.0) +
        tool * 0.3
    ))

    return {
        "total_cards": float(total),
        "pokemon_count": float(pokemon),
        "energy_count": float(energy),
        "trainer_count": float(trainer),
        "basic_pokemon_count": float(basic_pokemon),
        "stage1_count": float(stage1),
        "stage2_count": float(stage2),
        "evolution_count": float(stage1 + stage2),
        "ex_count": float(ex_count),
        "mega_ex_count": float(mega_ex_count),
        "ace_spec_count": float(ace_spec),
        "unique_pokemon": float(len(unique_pokemon)),
        "main_attacker_count": float(main_attacker),
        "secondary_attacker_count": float(secondary_attacker),
        "draw_support_count": float(draw_support),
        "search_count": float(search),
        "switch_count": float(switch),
        "gust_count": float(gust),
        "stadium_count": float(stadium),
        "tool_count": float(tool),
        "disruption_count": float(disruption),
        "dominant_energy_count": float(dominant_energy),
        "energy_diversity": float(energy_diversity),
        "avg_pokemon_hp": round(total_hp / pokemon, 1) if pokemon else 0.0,
        "avg_retreat_cost": round(total_retreat / pokemon, 2) if pokemon else 0.0,
        "estimated_consistency_score": round(consistency, 2),
        "estimated_attack_readiness_score": round(attack_readiness, 2),
        "estimated_counterplay_score": round(counterplay, 2),
    }


def features_to_json(card_ids: List[int]) -> str:
    return json.dumps(extract_features(card_ids), indent=2)
