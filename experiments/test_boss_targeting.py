"""
Tests for Boss's Orders target selection.

Run: python experiments/test_boss_targeting.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.policy import PolicyAgent

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0
_total = 0

def check(label, condition):
    global _failures, _total
    _total += 1
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        _failures += 1

agent = PolicyAgent.__new__(PolicyAgent)
agent.knowledge = type("K", (), {
    "get_role": lambda self, cid: {"265": "basic_attacker", "268": "evolution_base",
                                    "269": "engine_attacker", "271": "sub_attacker"}.get(cid, "unknown"),
    "get_priority_weight": lambda self, cid: 0.0,
    "attack_score": lambda self, cid: 0.0,
    "get": lambda self, cid: None,
    "has_tag": lambda self, cid, tag: False,
})()
agent.evaluator = type("E", (), {"is_active_in_danger": lambda self, s: False})()
agent.current_plan = None

STATE = {
    "your_index": 0,
    "active_pokemon": {
        "card_id": "269", "name": "Bellibolt ex", "is_ex": True,
        "energy_type": "Lightning", "hp_remaining": 250,
        "attacks": [{"attack_id": 1, "damage": 230}], "abilities": [],
    },
    "bench": [],
    "prizes_remaining": 4,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "999", "hp_remaining": 200},
        "bench": [
            {"card_id": "800", "name": "Low HP Mon", "is_ex": False,
             "hp_remaining": 40, "weakness": None, "resistance": None,
             "attacks": [], "abilities": []},
            {"card_id": "801", "name": "Ex Target", "is_ex": True,
             "hp_remaining": 200, "weakness": "Lightning", "resistance": None,
             "attacks": [], "abilities": []},
            {"card_id": "268", "name": "Tadbulb", "is_ex": False,
             "hp_remaining": 80, "weakness": None, "resistance": None,
             "attacks": [], "abilities": []},
        ],
    },
}

# ===================================================================
print("\n--- boss target: KO-able low HP ---")

action_low = {"type": 3, "area": 5, "index": 0, "playerIndex": 1, "select_context": 3}
score_low, reason_low = agent._score_boss_target(action_low, STATE)
check("Low HP target scored", score_low > 5)
check("Low HP reason has boss_low_hp", "boss_low_hp" in reason_low)

# ===================================================================
print("\n--- boss target: ex with weakness KO ---")

action_ex = {"type": 3, "area": 5, "index": 1, "playerIndex": 1, "select_context": 3}
score_ex, reason_ex = agent._score_boss_target(action_ex, STATE)
check("Ex target scored higher than low HP", score_ex > score_low)
check("Ex reason has boss_target_ex", "boss_target_ex" in reason_ex)
check("Ex reason has boss_can_ko", "boss_can_ko" in reason_ex)
check("Ex reason has boss_ko_ex", "boss_ko_ex" in reason_ex)

# ===================================================================
print("\n--- boss target: evolution base ---")

action_evo = {"type": 3, "area": 5, "index": 2, "playerIndex": 1, "select_context": 3}
score_evo, reason_evo = agent._score_boss_target(action_evo, STATE)
check("Evolution base scored", score_evo > 5)
check("Evolution base reason has key_support", "boss_key_support" in reason_evo)

# ===================================================================
print("\n--- dispatch: playerIndex routes to boss_target ---")

score_dispatch, reason_dispatch = agent._score_card_to_active(action_ex, STATE)
check("Dispatch routes opp to _score_boss_target", "boss_target" in reason_dispatch)

action_own = {"type": 3, "area": 5, "index": 0, "playerIndex": 0, "select_context": 3}
STATE_OWN = dict(STATE)
STATE_OWN["bench"] = [{"card_id": "265", "hp_remaining": 70, "energy_count": 2}]
score_own, reason_own = agent._score_card_to_active(action_own, STATE_OWN)
check("Dispatch routes own to _score_own_to_active", "to_active" in reason_own)

# ===================================================================
print("\n--- boss target: no playerIndex defaults to own ---")

action_no_pidx = {"type": 3, "area": 5, "index": 0, "select_context": 3}
score_no, reason_no = agent._score_card_to_active(action_no_pidx, STATE_OWN)
check("No playerIndex: routes to own", "to_active" in reason_no)

# ===================================================================
print("\n--- boss target: generic fallback ---")

action_bad = {"type": 3, "area": 5, "index": 99, "playerIndex": 1, "select_context": 3}
score_bad, reason_bad = agent._score_boss_target(action_bad, STATE)
check("Bad index: generic score", score_bad == 3.0)
check("Bad index: generic reason", "boss_target_generic" in reason_bad)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
