"""
Tests for agent/attack_plan.py.

Run: python experiments/test_attack_plan.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.attack_plan import (
    generate_attack_plans, select_best_plan, select_top_plans,
    get_cached_top_plans, clear_attack_plan_cache,
    plan_matches_action, AttackPlan,
)

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

# === Test states ===

STATE_KO = {
    "active_pokemon": {"card_id": "269", "name": "Bellibolt ex", "is_ex": True,
                       "energy_type": "Lightning", "hp_remaining": 250,
                       "attacks": [{"attack_id": 1, "damage": 230}], "abilities": []},
    "bench": [],
    "prizes_remaining": 2,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "999", "name": "Opp", "is_ex": True,
                           "hp_remaining": 200, "weakness": "Lightning",
                           "abilities": [], "attacks": []},
        "bench": [
            {"card_id": "888", "name": "Low HP", "is_ex": False, "hp_remaining": 40,
             "weakness": None, "abilities": [], "attacks": []},
        ],
    },
}

STATE_ZERO_DAMAGE = {
    "active_pokemon": {"card_id": "269", "name": "Bellibolt ex", "is_ex": True,
                       "energy_type": "Lightning", "hp_remaining": 250,
                       "attacks": [{"attack_id": 1, "damage": 230}], "abilities": []},
    "bench": [
        {"card_id": "265", "name": "Voltorb", "is_ex": False,
         "energy_type": "Lightning", "hp_remaining": 70, "energy_count": 2,
         "attacks": [{"attack_id": 2, "damage": 60}], "abilities": []},
    ],
    "prizes_remaining": 4,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "555", "name": "Wall Mon", "hp_remaining": 140,
                           "is_ex": False, "weakness": None, "resistance": None,
                           "abilities": [{"name": "Shell",
                            "text": "If this Pokemon would be damaged by an attack from your opponent's Pokemon ex, prevent that damage."}],
                           "attacks": []},
        "bench": [],
    },
}

STATE_BENCH_ATTACKER = {
    "active_pokemon": {"card_id": "268", "name": "Tadbulb", "is_ex": False,
                       "energy_type": "Lightning", "hp_remaining": 80,
                       "attacks": [{"attack_id": 5, "damage": 20}], "abilities": []},
    "bench": [
        {"card_id": "271", "name": "Kilowattrel", "is_ex": False,
         "energy_type": "Lightning", "hp_remaining": 120, "energy_count": 3,
         "attacks": [{"attack_id": 3, "damage": 70}], "abilities": []},
    ],
    "prizes_remaining": 4,
    "opponent": {
        "prizes_remaining": 4,
        "active_pokemon": {"card_id": "777", "name": "Opp", "hp_remaining": 60,
                           "is_ex": False, "abilities": [], "attacks": []},
        "bench": [],
    },
}

# ===================================================================
print("\n--- KO plan generation ---")

plans_ko = generate_attack_plans(STATE_KO)
check("Plans generated", len(plans_ko) > 0)
winning = [p for p in plans_ko if p.plan_type == "winning_ko"]
check("Winning KO plan found", len(winning) > 0)
if winning:
    check("Winning plan wins_game", winning[0].wins_game)
    check("Winning plan can_ko", winning[0].can_ko)
    check("Winning plan highest score", winning[0].plan_score == max(p.plan_score for p in plans_ko))

# ===================================================================
print("\n--- Boss KO plan ---")

boss_plans = [p for p in plans_ko if p.plan_type == "boss_ko"]
check("Boss KO plan found", len(boss_plans) > 0)
if boss_plans:
    check("Boss plan needs_boss", boss_plans[0].needs_boss)
    check("Boss plan can_ko", boss_plans[0].can_ko)

# ===================================================================
print("\n--- Zero damage escape plan ---")

plans_zd = generate_attack_plans(STATE_ZERO_DAMAGE)
escape = [p for p in plans_zd if p.plan_type == "zero_damage_escape"]
check("Zero damage escape plan found", len(escape) > 0)
if escape:
    check("Escape needs_switch", escape[0].needs_switch)
    check("Escape attacker is Voltorb", escape[0].attacker_cid == "265")
    check("Escape can_damage", escape[0].predicted_damage > 0)

# ===================================================================
print("\n--- Bench attacker plan ---")

plans_bench = generate_attack_plans(STATE_BENCH_ATTACKER)
kw_sub = [p for p in plans_bench if p.plan_type == "kilowattrel_sub_attacker"]
check("KW sub-attacker plan found (was bench_attacker)", len(kw_sub) > 0)
if kw_sub:
    check("Bench plan needs_switch", kw_sub[0].needs_switch)
    check("Bench plan KW can KO 60HP", kw_sub[0].can_ko)

# ===================================================================
print("\n--- select_best_plan ---")

best = select_best_plan(STATE_KO)
check("Best plan is winning_ko", best is not None and best.plan_type == "winning_ko")

best_zd = select_best_plan(STATE_ZERO_DAMAGE)
check("Best plan for zero dmg is escape", best_zd is not None and best_zd.plan_type == "zero_damage_escape")

# ===================================================================
print("\n--- plan_matches_action ---")

plan = AttackPlan(plan_type="winning_ko", attacker_cid="269", plan_score=1000, needs_boss=False, needs_switch=False)
atk_action = {"type": 13, "attackId": 1}
state_for_match = {"active_pokemon": {"card_id": "269"}, "your_index": 0}
bonus = plan_matches_action(plan, atk_action, state_for_match)
check("Attack matching plan gets bonus", bonus > 0)

non_matching = {"type": 14}
bonus_end = plan_matches_action(plan, non_matching, state_for_match)
check("End action gets no plan bonus", bonus_end == 0)

# Boss plan match
boss_plan = AttackPlan(plan_type="boss_ko", target_cid="888", plan_score=500, needs_boss=True)
boss_action = {"type": 3, "playerIndex": 1, "area": 5, "index": 0}
state_boss = {"active_pokemon": {"card_id": "269"}, "your_index": 0,
              "opponent": {"bench": [{"card_id": "888"}]}}
bonus_boss = plan_matches_action(boss_plan, boss_action, state_boss)
check("Boss action matching plan gets bonus", bonus_boss > 0)

# ===================================================================
print("\n--- voltorb_charge plan ---")

STATE_VOLTORB = {
    "active_pokemon": {"card_id": "268", "name": "Tadbulb", "is_ex": False,
                       "energy_type": "Lightning", "hp_remaining": 80,
                       "attacks": [{"damage": 20}], "abilities": []},
    "bench": [
        {"card_id": "265", "name": "Voltorb", "is_ex": False, "energy_type": "Lightning",
         "hp_remaining": 70, "energy_count": 1,
         "attacks": [{"attack_id": 2, "damage": 60}], "abilities": []},
        {"card_id": "269", "name": "Bellibolt ex", "is_ex": True, "energy_type": "Lightning",
         "hp_remaining": 250, "energy_count": 4, "attacks": [{"damage": 230}], "abilities": []},
    ],
    "prizes_remaining": 4,
    "opponent": {"prizes_remaining": 4,
                 "active_pokemon": {"card_id": "777", "hp_remaining": 100, "is_ex": False,
                                    "abilities": [], "attacks": []},
                 "bench": []},
}

plans_vt = generate_attack_plans(STATE_VOLTORB)
vt_plans = [p for p in plans_vt if p.plan_type == "voltorb_charge"]
check("Voltorb charge plan found", len(vt_plans) > 0)
if vt_plans:
    check("Voltorb needs energy (1/2)", vt_plans[0].needs_energy)
    check("Voltorb needs_bellibolt_ability", vt_plans[0].needs_bellibolt_ability)
    check("Voltorb needs_switch", vt_plans[0].needs_switch)

# ===================================================================
print("\n--- bellibolt_self_attack plan ---")

STATE_BB_SELF = {
    "active_pokemon": {"card_id": "269", "name": "Bellibolt ex", "is_ex": True,
                       "energy_type": "Lightning", "hp_remaining": 250, "energy_count": 3,
                       "attacks": [{"damage": 230}], "abilities": []},
    "bench": [],
    "prizes_remaining": 4,
    "opponent": {"prizes_remaining": 4,
                 "active_pokemon": {"card_id": "777", "hp_remaining": 200, "is_ex": False,
                                    "abilities": [], "attacks": []},
                 "bench": []},
}

plans_bb = generate_attack_plans(STATE_BB_SELF)
bb_self = [p for p in plans_bb if p.plan_type == "bellibolt_self_attack"]
check("Bellibolt self-attack plan found", len(bb_self) > 0)
if bb_self:
    check("BB self needs_bellibolt_ability (1 away)", bb_self[0].needs_bellibolt_ability)

# ===================================================================
print("\n--- kilowattrel_sub_attacker plan ---")

STATE_KW = {
    "active_pokemon": {"card_id": "268", "name": "Tadbulb", "is_ex": False,
                       "hp_remaining": 80, "attacks": [{"damage": 20}], "abilities": []},
    "bench": [
        {"card_id": "271", "name": "Kilowattrel", "is_ex": False, "energy_type": "Lightning",
         "hp_remaining": 120, "energy_count": 3,
         "attacks": [{"attack_id": 3, "damage": 70}], "abilities": []},
    ],
    "prizes_remaining": 4,
    "opponent": {"prizes_remaining": 4,
                 "active_pokemon": {"card_id": "777", "hp_remaining": 60, "is_ex": False,
                                    "abilities": [], "attacks": []},
                 "bench": []},
}

plans_kw = generate_attack_plans(STATE_KW)
kw_plans = [p for p in plans_kw if p.plan_type == "kilowattrel_sub_attacker"]
check("Kilowattrel sub-attacker plan found", len(kw_plans) > 0)
if kw_plans:
    check("KW can KO 60HP", kw_plans[0].can_ko)
    check("KW needs_switch", kw_plans[0].needs_switch)

# ===================================================================
print("\n--- select_top_plans ---")

top3 = select_top_plans(STATE_KO, limit=3)
check("Top plans returns list", isinstance(top3, list))
check("Top plans <= 3", len(top3) <= 3)
check("Top plans sorted by score", all(top3[i].plan_score >= top3[i+1].plan_score for i in range(len(top3)-1)))

# ===================================================================
print("\n--- top plans bonus fallback ---")

# Boss plan is best but no Boss action; second plan matches attack
plan_boss = AttackPlan(plan_type="boss_ko", target_cid="888", plan_score=600, needs_boss=True)
plan_atk = AttackPlan(plan_type="active_ko", attacker_cid="269", plan_score=300, needs_boss=False, needs_switch=False)
atk_act = {"type": 13, "attackId": 1}
st = {"active_pokemon": {"card_id": "269"}, "your_index": 0}

b1 = plan_matches_action(plan_boss, atk_act, st)
b2 = plan_matches_action(plan_atk, atk_act, st)
check("Boss plan no match for attack", b1 == 0)
check("Active plan matches attack", b2 > 0)
check("Top plans would give bonus from 2nd plan", max(b1, b2) > 0)

# ===================================================================
print("\n--- cache ---")

clear_attack_plan_cache()
cached1 = get_cached_top_plans(STATE_KO, limit=3)
check("Cache returns list", isinstance(cached1, list))
check("Cache has plans", len(cached1) > 0)

cached2 = get_cached_top_plans(STATE_KO, limit=3)
check("Same state: same plans", [p.plan_type for p in cached1] == [p.plan_type for p in cached2])

clear_attack_plan_cache()
cached3 = get_cached_top_plans(STATE_KO, limit=3)
check("After clear: same result", [p.plan_type for p in cached1] == [p.plan_type for p in cached3])

direct = select_top_plans(STATE_KO, limit=3)
check("Cache matches direct", [p.plan_type for p in cached1] == [p.plan_type for p in direct])

cached_none = get_cached_top_plans(None, limit=3)
check("Cache None state: no crash", isinstance(cached_none, list))

cached_empty = get_cached_top_plans({}, limit=3)
check("Cache empty state: no crash", isinstance(cached_empty, list))

# ===================================================================
print("\n--- empty state safety ---")

plans_empty = generate_attack_plans({})
check("Empty state: no crash, no plans", len(plans_empty) == 0)

plans_none = generate_attack_plans(None)
check("None state: no crash", len(plans_none) == 0)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
