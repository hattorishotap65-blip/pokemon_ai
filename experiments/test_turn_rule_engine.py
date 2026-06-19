"""
Tests for turn_rule_engine.py.

Covers:
  1. Option classification (attack, ability, retreat, end, energy_attach)
  2. rule_score_option: attack gets +150
  3. rule_score_option: end/retreat get -1000 when attack is available
  4. rule_score_option: end/retreat get mild penalty when no attack available
  5. rule_score_option: ability gets +5 or +15 depending on attack availability
  6. rule_score_option: energy attach gets 0 or +10 depending on attack availability
  7. classify_option returns correct class strings
  8. has_legal_attack_option only True when type=13 + attackId

Run: python experiments/test_turn_rule_engine.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.turn_rule_engine import (
    is_attack_option, is_ability_option, is_retreat_option, is_end_option,
    is_energy_attach_option, is_turn_ending_option, can_continue_after_option,
    has_legal_attack_option, classify_option, rule_score_option,
    option_debug_record, select_summary,
)

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
# Test fixtures
# ---------------------------------------------------------------------------

def _make_select(*opts):
    """Build a synthetic select dict from option dicts."""
    return {"option": list(opts)}

ATK_OPT     = {"type": 13, "attackId": 368}
ATK_NO_ID   = {"type": 13, "attackId": None}
ABILITY_OPT = {"type": 10, "cardId": "269"}
RETREAT_OPT = {"type": 12}
END_OPT     = {"type": 14}
ATTACH_OPT  = {"type": 8, "inPlayArea": 4}
PLAY_OPT    = {"type": 7, "cardId": "265"}

SELECT_WITH_ATTACK    = _make_select(ATK_OPT, RETREAT_OPT, END_OPT, ABILITY_OPT)
SELECT_WITHOUT_ATTACK = _make_select(ABILITY_OPT, RETREAT_OPT, END_OPT)
SELECT_ONLY_END       = _make_select(END_OPT)
STATE_EMPTY = {}


# ---------------------------------------------------------------------------
# 1. Option classification
# ---------------------------------------------------------------------------
print("\n--- Option classification ---")

check("ATK_OPT    -> is_attack_option True",    is_attack_option(ATK_OPT))
check("ATK_NO_ID  -> is_attack_option False",   not is_attack_option(ATK_NO_ID))
check("RETREAT    -> is_retreat_option True",   is_retreat_option(RETREAT_OPT))
check("RETREAT    -> is_attack_option False",   not is_attack_option(RETREAT_OPT))
check("ABILITY    -> is_ability_option True",   is_ability_option(ABILITY_OPT))
check("END        -> is_end_option True",       is_end_option(END_OPT))
check("ATTACH     -> is_energy_attach True",    is_energy_attach_option(ATTACH_OPT))
check("ATTACH     -> is_attack False",          not is_attack_option(ATTACH_OPT))
check("ATK        -> is_turn_ending True",      is_turn_ending_option(ATK_OPT))
check("END        -> is_turn_ending True",      is_turn_ending_option(END_OPT))
check("ABILITY    -> is_turn_ending False",     not is_turn_ending_option(ABILITY_OPT))
check("RETREAT    -> is_turn_ending False",     not is_turn_ending_option(RETREAT_OPT))
check("ATK        -> can_continue_after False", not can_continue_after_option(ATK_OPT))
check("ABILITY    -> can_continue_after True",  can_continue_after_option(ABILITY_OPT))


# ---------------------------------------------------------------------------
# 2. has_legal_attack_option
# ---------------------------------------------------------------------------
print("\n--- has_legal_attack_option ---")

check("Select with ATK_OPT       -> True",  has_legal_attack_option(SELECT_WITH_ATTACK))
check("Select without ATK_OPT    -> False", not has_legal_attack_option(SELECT_WITHOUT_ATTACK))
check("Select with ATK_NO_ID     -> False", not has_legal_attack_option(_make_select(ATK_NO_ID)))
check("Empty select              -> False", not has_legal_attack_option({}))


# ---------------------------------------------------------------------------
# 3. rule_score_option: attack
# ---------------------------------------------------------------------------
print("\n--- rule_score: attack ---")

atk_score, atk_reason = rule_score_option(ATK_OPT, STATE_EMPTY, SELECT_WITH_ATTACK)
check("Attack scores +150",                    atk_score == 150.0)
check("Attack reason is legal_attack_*",       "legal_attack" in atk_reason)


# ---------------------------------------------------------------------------
# 4. rule_score_option: end/retreat when attack available
# ---------------------------------------------------------------------------
print("\n--- rule_score: end/retreat with attack available ---")

end_w_atk, end_w_atk_r = rule_score_option(END_OPT, STATE_EMPTY, SELECT_WITH_ATTACK)
check("End scores -1000 when attack available",     end_w_atk == -1000.0)
check("End reason contains avoid_end_when_attack",  "avoid_end_when_attack" in end_w_atk_r)

ret_w_atk, ret_w_atk_r = rule_score_option(RETREAT_OPT, STATE_EMPTY, SELECT_WITH_ATTACK)
check("Retreat scores -1000 when attack available",        ret_w_atk == -1000.0)
check("Retreat reason contains avoid_retreat_when_attack", "avoid_retreat_when_attack" in ret_w_atk_r)


# ---------------------------------------------------------------------------
# 5. rule_score_option: end/retreat without attack available
# ---------------------------------------------------------------------------
print("\n--- rule_score: end/retreat without attack ---")

end_no_atk, end_no_atk_r = rule_score_option(END_OPT, STATE_EMPTY, SELECT_WITHOUT_ATTACK)
check("End score > -1000 when no attack (mild penalty)",  end_no_atk > -1000.0)
check("End score is negative",                            end_no_atk < 0)

ret_no_atk, _ = rule_score_option(RETREAT_OPT, STATE_EMPTY, SELECT_WITHOUT_ATTACK)
check("Retreat score > -1000 when no attack", ret_no_atk > -1000.0)
check("Retreat score is negative",            ret_no_atk < 0)


# ---------------------------------------------------------------------------
# 6. rule_score_option: ability
# ---------------------------------------------------------------------------
print("\n--- rule_score: ability ---")

ab_w_atk, ab_w_atk_r = rule_score_option(ABILITY_OPT, STATE_EMPTY, SELECT_WITH_ATTACK)
check("Ability score > 0 when attack available",      ab_w_atk > 0)
check("Ability score <= 15 when attack available",    ab_w_atk <= 15.0)
check("Ability reason contains ability_before_attack", "ability_before_attack" in ab_w_atk_r)

ab_no_atk, ab_no_atk_r = rule_score_option(ABILITY_OPT, STATE_EMPTY, SELECT_WITHOUT_ATTACK)
check("Ability score >= 15 when no attack available",  ab_no_atk >= 15.0)
check("Ability reason contains ability_can_continue",  "ability_can_continue" in ab_no_atk_r)


# ---------------------------------------------------------------------------
# 7. rule_score_option: energy attach
# ---------------------------------------------------------------------------
print("\n--- rule_score: energy attach ---")

at_w_atk, at_w_atk_r = rule_score_option(ATTACH_OPT, STATE_EMPTY, SELECT_WITH_ATTACK)
check("Attach score == 0 when attack available",        at_w_atk == 0.0)
check("Attach reason attach_optional_when_attack_*",   "attach_optional" in at_w_atk_r)

at_no_atk, at_no_atk_r = rule_score_option(ATTACH_OPT, STATE_EMPTY, SELECT_WITHOUT_ATTACK)
check("Attach score > 0 when no attack available",      at_no_atk > 0.0)
check("Attach reason attach_can_continue_turn",         "attach_can_continue" in at_no_atk_r)


# ---------------------------------------------------------------------------
# 8. classify_option
# ---------------------------------------------------------------------------
print("\n--- classify_option ---")

check("ATK_OPT    -> 'attack'",       classify_option(ATK_OPT)     == "attack")
check("ABILITY    -> 'ability'",      classify_option(ABILITY_OPT) == "ability")
check("RETREAT    -> 'retreat'",      classify_option(RETREAT_OPT) == "retreat")
check("END        -> 'end'",          classify_option(END_OPT)     == "end")
check("ATTACH     -> 'energy_attach'", classify_option(ATTACH_OPT) == "energy_attach")
check("PLAY       -> unknown_type_7",  "unknown" in classify_option(PLAY_OPT))


# ---------------------------------------------------------------------------
# 9. option_debug_record keys
# ---------------------------------------------------------------------------
print("\n--- option_debug_record ---")

dbg = option_debug_record(ATK_OPT, STATE_EMPTY, SELECT_WITH_ATTACK)
check("debug has option_class",            "option_class" in dbg)
check("debug has is_attack",               "is_attack" in dbg)
check("debug has is_ability",              "is_ability" in dbg)
check("debug has is_retreat",              "is_retreat" in dbg)
check("debug has is_end",                  "is_end" in dbg)
check("debug has is_turn_ending",          "is_turn_ending" in dbg)
check("debug has can_continue_after",      "can_continue_after" in dbg)
check("debug has has_legal_attack_option", "has_legal_attack_option" in dbg)
check("ATK debug: option_class == attack",  dbg["option_class"] == "attack")
check("ATK debug: is_attack == True",       dbg["is_attack"] is True)
check("ATK debug: has_legal_attack_option", dbg["has_legal_attack_option"] is True)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
total = 47
print(f"  Passed: {total - _failures}/{total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
