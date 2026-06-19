"""
Evaluates how close the current board state is to the win condition
defined in deck_profile.json.

Returns plan_progress_score: float in ~0-10 range.
Higher = we're on track toward our win condition.
"""


# ---------------------------------------------------------------------------
# Phase detection
# ---------------------------------------------------------------------------

def detect_current_phase(state: dict) -> str:
    """Return 'early', 'mid', or 'late' based on board state."""
    turn    = int(state.get("turn", 0) or 0)
    prizes  = int(state.get("prizes_remaining", 6) or 6)

    if prizes <= 2 or turn >= 10:
        return "late"
    if turn <= 3 or prizes >= 5:
        return "early"
    return "mid"


# ---------------------------------------------------------------------------
# Phase-specific progress evaluators
# ---------------------------------------------------------------------------

def evaluate_early_plan_progress(state: dict, deck_profile: dict, knowledge) -> float:
    """
    Early game: basics in play, bench set up, energy attached, draw active.
    Returns 0-10.
    """
    score = 0.0

    active = state.get("active_pokemon", {})
    bench  = state.get("bench", []) or []

    # Active pokemon exists
    if active.get("card_id"):
        score += 2.0

    # Bench at least 1
    bench_count = len([p for p in bench if p.get("card_id")])
    score += min(bench_count, 3) * 1.0  # up to +3

    # At least one setup card on bench
    setup_ids = set(str(x) for x in (deck_profile or {}).get("setup_cards", []))
    if knowledge and setup_ids:
        for p in bench:
            cid = str(p.get("card_id", ""))
            if cid in setup_ids or knowledge.get_role(cid) in ("basic_setup", "evolution_base"):
                score += 1.5
                break

    # Energy on active
    energy_count = int(active.get("energy_count", 0) or 0)
    if energy_count >= 1:
        score += 1.5
    elif energy_count >= 2:
        score += 0.5  # additional

    # Hand not empty (draw engine working)
    hand_count = int(state.get("hand_count", 0) or 0)
    if hand_count >= 4:
        score += 1.0
    elif hand_count == 0:
        score -= 2.0

    # Main attacker candidate on bench
    attacker_ids = set(str(x) for x in (deck_profile or {}).get("main_attackers", []))
    if knowledge and attacker_ids:
        for p in bench:
            if str(p.get("card_id", "")) in attacker_ids:
                score += 1.5
                break

    return min(max(score, 0.0), 10.0)


def evaluate_mid_plan_progress(state: dict, deck_profile: dict, knowledge) -> float:
    """
    Mid game: attacker evolved/ready, attacking, prize race not behind.
    Returns 0-10.
    """
    score = 0.0

    active     = state.get("active_pokemon", {})
    bench      = state.get("bench", []) or []
    prizes     = int(state.get("prizes_remaining", 6) or 6)
    opp_prizes = int(state.get("opponent", {}).get("prizes_remaining", 6) or 6)

    # Main attacker is active
    attacker_ids = set(str(x) for x in (deck_profile or {}).get("main_attackers", []))
    active_cid = str(active.get("card_id", ""))
    if active_cid in attacker_ids:
        score += 3.0
        # Energised
        if int(active.get("energy_count", 0) or 0) >= 2:
            score += 2.0
        elif int(active.get("energy_count", 0) or 0) >= 1:
            score += 1.0
    elif knowledge and knowledge.get_role(active_cid) == "main_attacker":
        score += 2.0

    # Next attacker ready on bench
    for p in bench:
        cid = str(p.get("card_id", ""))
        if cid in attacker_ids or (knowledge and knowledge.get_role(cid) in ("main_attacker", "sub_attacker")):
            if int(p.get("energy_count", 0) or 0) >= 1:
                score += 1.5
                break
            else:
                score += 0.5
                break

    # Prize race: not behind
    if prizes <= opp_prizes:
        score += 1.0
    if prizes < opp_prizes:
        score += 1.0  # bonus for leading

    # Hand adequate
    if int(state.get("hand_count", 0) or 0) >= 3:
        score += 0.5

    return min(max(score, 0.0), 10.0)


def evaluate_late_plan_progress(state: dict, deck_profile: dict, knowledge) -> float:
    """
    Late game: can take remaining prizes, no deck-out risk, finisher ready.
    Returns 0-10.
    """
    score = 0.0

    active     = state.get("active_pokemon", {})
    prizes     = int(state.get("prizes_remaining", 6) or 6)
    opp_prizes = int(state.get("opponent", {}).get("prizes_remaining", 6) or 6)
    deck_count = int(state.get("deck_count", 20) or 20)

    # Leading in prizes
    if prizes < opp_prizes:
        score += 3.0
    elif prizes == opp_prizes:
        score += 1.5

    # Attacker ready to close out (main or backup/sub)
    dp = deck_profile or {}
    main_ids  = set(str(x) for x in dp.get("main_attackers", []))
    backup_ids = set(str(x) for x in dp.get("sub_attackers", []))
    backup_ids.update(str(x) for x in dp.get("backup_attackers", []))
    all_attacker_ids = main_ids | backup_ids
    active_cid   = str(active.get("card_id", ""))
    active_energy = int(active.get("energy_count", 0) or 0)

    if active_cid in main_ids and active_energy >= 1:
        score += 3.0
    elif active_cid in backup_ids and active_energy >= 1:
        score += 2.0
    elif knowledge and knowledge.get_role(active_cid) in ("main_attacker", "sub_attacker") and active_energy >= 1:
        score += 2.0

    # No deck-out risk
    if deck_count > 5:
        score += 1.0
    elif deck_count <= 3:
        score -= 3.0

    # Hand has something (not top-decking)
    if int(state.get("hand_count", 0) or 0) >= 2:
        score += 1.0

    # Finisher accessible (winning KO in reach)
    if prizes <= 2 and active_cid in all_attacker_ids:
        score += 2.0
    elif prizes <= 2 and knowledge and knowledge.get_role(active_cid) in ("main_attacker", "sub_attacker"):
        score += 1.5

    return min(max(score, 0.0), 10.0)


# ---------------------------------------------------------------------------
# Missing plan pieces
# ---------------------------------------------------------------------------

def get_missing_plan_pieces(state: dict, deck_profile: dict, knowledge) -> list:
    """
    Return a list of string descriptions of things still needed.
    Used for logging and analysis.
    """
    if not deck_profile:
        return []

    missing = []
    active  = state.get("active_pokemon", {})
    bench   = state.get("bench", []) or []
    phase   = detect_current_phase(state)

    attacker_ids = set(str(x) for x in deck_profile.get("main_attackers", []))
    attacker_ids.update(str(x) for x in deck_profile.get("sub_attackers", []))
    attacker_ids.update(str(x) for x in deck_profile.get("backup_attackers", []))
    active_cid   = str(active.get("card_id", ""))

    # Any attacker not yet active or benched
    attacker_on_field = (active_cid in attacker_ids) or any(
        str(p.get("card_id", "")) in attacker_ids for p in bench
    )
    if not attacker_on_field:
        missing.append("main_attacker_not_in_play")

    # Energy starved
    if int(active.get("energy_count", 0) or 0) == 0:
        missing.append("no_energy_on_active")

    # Bench empty
    if len([p for p in bench if p.get("card_id")]) == 0:
        missing.append("bench_empty")

    # Hand drought
    if int(state.get("hand_count", 0) or 0) <= 1:
        missing.append("low_hand_count")

    # Deck-out risk
    if int(state.get("deck_count", 20) or 20) <= 5:
        missing.append("deck_out_risk")

    # Prize race behind in mid/late
    prizes     = int(state.get("prizes_remaining", 6) or 6)
    opp_prizes = int(state.get("opponent", {}).get("prizes_remaining", 6) or 6)
    if phase in ("mid", "late") and prizes > opp_prizes + 1:
        missing.append("prize_race_behind")

    return missing


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate_plan_progress(state: dict, deck_profile: dict, knowledge) -> float:
    """
    Return overall plan_progress_score in ~0-10 range.
    Dispatches to the appropriate phase evaluator.
    """
    try:
        phase = detect_current_phase(state)
        if phase == "early":
            return evaluate_early_plan_progress(state, deck_profile, knowledge)
        if phase == "late":
            return evaluate_late_plan_progress(state, deck_profile, knowledge)
        return evaluate_mid_plan_progress(state, deck_profile, knowledge)
    except Exception:
        return 0.0
