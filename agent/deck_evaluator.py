"""
Evaluate deck composition to produce aggregated metrics.
Used by deck_analyzer.py to derive archetype and confidence.
All inputs are plain dicts; no cg.api dependency.
"""
from collections import Counter


def evaluate(deck_card_ids: list[int], knowledge) -> dict:
    """
    Given a list of card IDs (60) and a CardKnowledge instance,
    return a dict of deck-level metrics.
    """
    total = len(deck_card_ids) or 1
    unique_ids = list(dict.fromkeys(deck_card_ids))

    roles    = Counter()
    sub_roles = Counter()
    adv_sums: dict[str, float] = {}
    concept_tag_counts: Counter = Counter()
    win_tag_counts: Counter     = Counter()

    adv_keys = (
        "card_adv", "board_adv", "energy_adv", "tempo_adv",
        "prize_adv", "resource_adv", "info_adv", "risk_reduction_adv",
    )
    for k in adv_keys:
        adv_sums[k] = 0.0

    for cid in deck_card_ids:
        info = knowledge.get(str(cid))
        if info is None:
            continue
        roles[info["role"]] += 1
        if info["sub_role"]:
            sub_roles[info["sub_role"]] += 1
        for k in adv_keys:
            adv_sums[k] += info.get(k, 0)
        for tag in info.get("concept_tags", set()):
            concept_tag_counts[tag] += 1
        for tag in info.get("win_condition_tags", set()):
            win_tag_counts[tag] += 1

    # Role ratios (per card in deck)
    role_ratio = {r: c / total for r, c in roles.items()}

    # Avg adv values
    avg_adv = {k: round(adv_sums[k] / total, 2) for k in adv_keys}

    # Energy count
    energy_count = (
        roles.get("energy", 0)
        + roles.get("energy_special", 0)
        + roles.get("energy_restricted", 0)
    )

    # Setup cards: evolution_base + basic_setup
    setup_count = roles.get("evolution_base", 0) + roles.get("basic_setup", 0)

    # Evolution line exists — check roles AND stage tags (basic_setup = Dwebble type)
    has_stage_pokemon = any(
        "stage1" in (knowledge.get(str(c)) or {}).get("tags", set())
        or "stage2" in (knowledge.get(str(c)) or {}).get("tags", set())
        for c in unique_ids
    )
    has_evolution = (
        roles.get("evolution_base", 0) > 0
        or roles.get("evolution_bridge", 0) > 0
        or roles.get("basic_setup", 0) > 0
        or has_stage_pokemon
    )

    # Identify specific card groups by role
    attackers  = [c for c in unique_ids if knowledge.get_role(str(c)) == "main_attacker"]
    sub_atk    = [c for c in unique_ids if knowledge.get_role(str(c)) == "sub_attacker"]
    draw_eng   = [c for c in unique_ids if knowledge.get_role(str(c)) in ("draw", "search_engine")]
    search_eng = [c for c in unique_ids if knowledge.get_role(str(c)) == "search"]
    energy_eng = [c for c in unique_ids if knowledge.get_role(str(c)) in ("energy_search", "energy_support")]
    disruption = [c for c in unique_ids if knowledge.get_role(str(c)) in ("disruption", "removal")]
    recovery   = [c for c in unique_ids if knowledge.get_role(str(c)) == "recovery"]
    setup_cds  = [c for c in unique_ids
                  if knowledge.get_role(str(c)) in ("evolution_base", "basic_setup", "evolve")]

    # Derived composite metrics
    search_ratio     = role_ratio.get("search", 0) + role_ratio.get("energy_search", 0)
    draw_ratio       = role_ratio.get("draw", 0) + role_ratio.get("search_engine", 0)
    disruption_ratio = role_ratio.get("disruption", 0) + role_ratio.get("removal", 0)
    recovery_ratio   = role_ratio.get("recovery", 0)
    attacker_ratio   = role_ratio.get("main_attacker", 0) + role_ratio.get("sub_attacker", 0)
    energy_ratio     = energy_count / total
    combo_tag_ratio  = concept_tag_counts.get("combo", 0) / total

    # Attack-readiness estimate
    avg_attack_score = 0.0
    for cid in unique_ids:
        info = knowledge.get(str(cid))
        if info:
            avg_attack_score += info.get("attack_score", 0)
    if unique_ids:
        avg_attack_score /= len(unique_ids)

    # Energy consistency: enough energy + search
    energy_search_count = roles.get("energy_search", 0)
    energy_consistency  = min(
        (energy_count + energy_search_count * 2) / 20.0, 1.0
    )

    # Dead card rate estimate: low use_score cards
    dead_count = 0
    for cid in deck_card_ids:
        info = knowledge.get(str(cid))
        if info and info.get("use_score", 5) <= 3:
            dead_count += 1
    dead_card_rate = dead_count / total

    # Main attacker access: how many copies of best attacker
    best_attacker_copies = 0
    if attackers:
        best_attacker_copies = deck_card_ids.count(attackers[0])
    main_attacker_access = min(best_attacker_copies / 4.0, 1.0)

    return {
        # Role distribution
        "roles":              dict(roles),
        "role_ratio":         {k: round(v, 3) for k, v in role_ratio.items()},
        # Adv averages
        **{f"avg_{k}": v for k, v in avg_adv.items()},
        # Aggregate ratios
        "attacker_ratio":     round(attacker_ratio, 3),
        "energy_ratio":       round(energy_ratio, 3),
        "search_ratio":       round(search_ratio, 3),
        "draw_ratio":         round(draw_ratio, 3),
        "disruption_ratio":   round(disruption_ratio, 3),
        "recovery_ratio":     round(recovery_ratio, 3),
        "combo_tag_ratio":    round(combo_tag_ratio, 3),
        "has_evolution":      has_evolution,
        # Derived quality metrics
        "avg_attack_score":         round(avg_attack_score, 2),
        "energy_consistency_score": round(energy_consistency, 3),
        "main_attacker_access_score": round(main_attacker_access, 3),
        "dead_card_rate":            round(dead_card_rate, 3),
        # Card lists by role (IDs)
        "main_attackers":   attackers,
        "sub_attackers":    sub_atk,
        "draw_engine":      draw_eng,
        "search_engine":    search_eng,
        "energy_engine":    energy_eng,
        "disruption_cards": disruption,
        "recovery_cards":   recovery,
        "setup_cards":      setup_cds,
        # Concept/win-condition tag distribution
        "concept_tag_counts":      dict(concept_tag_counts),
        "win_condition_tag_counts": dict(win_tag_counts),
    }
