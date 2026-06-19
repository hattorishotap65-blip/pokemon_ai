"""
Tests for score_kilowattrel_ability() in ionos_rules.py.

Cases per spec:
  Case 1: Active=Kilowattrel, energy=3, hand=5, attack available
          → Ability avoided (-250, avoid_ability_when_attack_available)
  Case 2: Active=Kilowattrel, energy=3, hand=2, attack available
          → Ability avoided: discarding breaks attack-ready state (-300)
  Case 3: Active=Kilowattrel, energy=2, hand=2, no attack, setup poor
          → Ability high score (low_hand + setup_poor + no_attack)
  Case 4: Active=Kilowattrel, energy=1, hand=5, no attack
          → Ability avoided (large hand -120)
  Extra: Non-Kilowattrel ability returns 0
  Extra: Non-ability option returns 0
  Extra: Kilowattrel energy=1, hand=2, no attack → energy_too_low penalty

Run: python experiments/test_kilowattrel_ability.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.ionos_rules import score_kilowattrel_ability

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0

def check(label: str, condition: bool):
    global _failures
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        _failures += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ability_opt(card_id: str) -> dict:
    return {"type": 10, "resolved_card_id": card_id, "attackId": None}

def _make_attack_opt() -> dict:
    return {"type": 13, "attackId": 999, "resolved_card_id": None}

def _make_end_opt() -> dict:
    return {"type": 14, "resolved_card_id": None}

def _make_select(*opts) -> dict:
    return {"option": list(opts)}

def _make_state(active_cid: str, active_energy: int, hand_count: int,
                bench: list = None, setup_poor: bool = False) -> dict:
    """Build minimal state dict for testing."""
    hand_ids = ["4"] * min(hand_count, 3)  # some Lightning placeholders
    state = {
        "active_pokemon": {
            "card_id": active_cid,
            "energy_count": active_energy,
            "hp_remaining": 120,
            "energy_types": ["4"] * active_energy,
        },
        "bench": bench or [],
        "hand": hand_ids,
        "hand_count": hand_count,
        "prizes_remaining": 3,
        "opponent": {"active_pokemon": {"card_id": "99", "hp_remaining": 100}, "prizes_remaining": 3},
        "energyAttached": False,
    }
    if setup_poor:
        # Force setup_poor by emptying bench
        state["bench"] = []
    return state


KW_ABILITY = _make_ability_opt("271")
BELLI_ABILITY = _make_ability_opt("269")
ATTACK_OPT = _make_attack_opt()
END_OPT    = _make_end_opt()

SELECT_WITH_ATTACK    = _make_select(ATTACK_OPT, KW_ABILITY, END_OPT)
SELECT_WITHOUT_ATTACK = _make_select(KW_ABILITY, END_OPT)


# ---------------------------------------------------------------------------
# Case 1: energy=3, hand=5, attack available → avoid ability
# ---------------------------------------------------------------------------
print("\n--- Case 1: energy=3, hand=5, attack available ---")

state1 = _make_state("271", active_energy=3, hand_count=5)
score1, reason1 = score_kilowattrel_ability(KW_ABILITY, state1, SELECT_WITH_ATTACK)
check("Score <= -250",                            score1 <= -250.0)
check("Reason: avoid_ability_when_attack_available",
      "avoid_ability_when_attack_available" in reason1)


# ---------------------------------------------------------------------------
# Case 2: energy=3, hand=2, attack available → breaks attack state
# ---------------------------------------------------------------------------
print("\n--- Case 2: energy=3, hand=2, attack available (breaks state) ---")

state2 = _make_state("271", active_energy=3, hand_count=2)
score2, reason2 = score_kilowattrel_ability(KW_ABILITY, state2, SELECT_WITH_ATTACK)
# Attack available + can_attack_now → -250 fires first (before -300 check)
check("Score <= -250 (attack available overrides)", score2 <= -250.0)

# Without attack option, only breaks_attack_ready_state applies
score2b, reason2b = score_kilowattrel_ability(KW_ABILITY, state2, SELECT_WITHOUT_ATTACK)
check("Score <= -300 when no attack but breaks state",  score2b <= -300.0)
check("Reason: kilowattrel_ability_breaks_attack_ready_state",
      "breaks_attack_ready_state" in reason2b)


# ---------------------------------------------------------------------------
# Case 3: energy=2, hand=2, no attack, poor setup → high score
# ---------------------------------------------------------------------------
print("\n--- Case 3: energy=2, hand=2, no attack, poor setup ---")

state3 = _make_state("271", active_energy=2, hand_count=2, setup_poor=True)
score3, reason3 = score_kilowattrel_ability(KW_ABILITY, state3, SELECT_WITHOUT_ATTACK)
check("Score > 0 (ability encouraged)",            score3 > 0.0)
check("Reason contains kilowattrel_ability_low_hand",
      "kilowattrel_ability_low_hand" in reason3)
check("Reason contains kilowattrel_ability_very_low_hand",
      "kilowattrel_ability_very_low_hand" in reason3)
check("Reason contains kilowattrel_ability_setup_poor",
      "kilowattrel_ability_setup_poor" in reason3)
check("Reason contains kilowattrel_ability_no_attack_available",
      "kilowattrel_ability_no_attack_available" in reason3)
# Score should be high: 80 (low_hand) + 50 (very_low) + 50 (setup_poor) + 30 (no_atk) = 210
check("Score >= 180",                              score3 >= 180.0)


# ---------------------------------------------------------------------------
# Case 4: energy=1, hand=5, no attack → large hand penalty
# ---------------------------------------------------------------------------
print("\n--- Case 4: energy=1, hand=5, no attack ---")

state4 = _make_state("271", active_energy=1, hand_count=5)
score4, reason4 = score_kilowattrel_ability(KW_ABILITY, state4, SELECT_WITHOUT_ATTACK)
check("Score <= -120 (large hand)",                score4 <= -120.0)
check("Reason: kilowattrel_avoid_ability_with_large_hand",
      "avoid_ability_with_large_hand" in reason4)


# ---------------------------------------------------------------------------
# Extra: energy=1, hand=2, no attack → low energy penalty applied
# ---------------------------------------------------------------------------
print("\n--- Extra: energy=1, hand=2, no attack (energy_too_low penalty) ---")

state5 = _make_state("271", active_energy=1, hand_count=2)
score5, reason5 = score_kilowattrel_ability(KW_ABILITY, state5, SELECT_WITHOUT_ATTACK)
# 80 (low_hand) + 50 (very_low) + 30 (no_atk) - 80 (energy_too_low) = 80
check("Reason contains energy_too_low",            "energy_too_low" in reason5)
# Score should be reduced by energy_too_low penalty
check("Score < 160 (energy_too_low applied)",      score5 < 160.0)


# ---------------------------------------------------------------------------
# Extra: Non-Kilowattrel ability → returns 0
# ---------------------------------------------------------------------------
print("\n--- Extra: non-Kilowattrel ability returns 0 ---")

state6 = _make_state("269", active_energy=3, hand_count=2)
score6, reason6 = score_kilowattrel_ability(BELLI_ABILITY, state6, SELECT_WITHOUT_ATTACK)
check("Bellibolt ability returns 0.0",             score6 == 0.0)
check("Reason is empty",                           reason6 == "")

# Non-ability option returns 0
score7, _ = score_kilowattrel_ability(ATTACK_OPT, state6, SELECT_WITHOUT_ATTACK)
check("Attack opt returns 0.0",                    score7 == 0.0)


# ---------------------------------------------------------------------------
# Extra: select=None (no select context) → no attack known
# ---------------------------------------------------------------------------
print("\n--- Extra: select=None (no context available) ---")

state8 = _make_state("271", active_energy=3, hand_count=2)
score8, reason8 = score_kilowattrel_ability(KW_ABILITY, state8, select=None)
# No attack context: can_attack_now=True but has_attack=False → breaks_attack_ready_state fires
check("No select: breaks_attack_ready_state fires", "breaks_attack_ready_state" in reason8)
check("No select: score <= -300",                   score8 <= -300.0)


# ---------------------------------------------------------------------------
# Extra: energy=4 (can attack AND can attack after discard)
# ---------------------------------------------------------------------------
print("\n--- Extra: energy=4, hand=2, no attack available ---")

state9 = _make_state("271", active_energy=4, hand_count=2)
score9, reason9 = score_kilowattrel_ability(KW_ABILITY, state9, SELECT_WITHOUT_ATTACK)
# can_attack_now=True (energy>=3), can_attack_after_discard=True (3>=3)
# has_attack=False → breaks_attack_ready_state does NOT fire
# hand_count=2 → 80 (low) + 50 (very_low) + 30 (no_atk) = 160
check("energy=4 + hand=2 + no attack: score > 0",  score9 > 0.0)
check("Reason: low_hand",                           "kilowattrel_ability_low_hand" in reason9)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = 21
print(f"\n{'='*50}")
print(f"  Passed: {total - _failures}/{total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
