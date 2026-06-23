"""
Tests for attack_plan diagnostics functions.

Run: python experiments/test_attack_plan_diagnostics.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.attack_plan import (
    AttackPlan, summarize_attack_plans, diagnose_attack_plan_choice,
    plan_matches_action,
    get_attached_energy_count, get_attack_energy_requirement, has_attack_energy,
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

# ===================================================================
print("\n--- summarize_attack_plans ---")

# Empty
s_empty = summarize_attack_plans([])
check("Empty: plan_count=0", s_empty["plan_count"] == 0)
check("Empty: best_plan_type empty", s_empty["best_plan_type"] == "")
check("Empty: no KO flags", not s_empty["has_winning_ko"] and not s_empty["has_active_ko"])

# winning_ko + boss_ko
plans_ko = [
    AttackPlan(plan_type="winning_ko", plan_score=1050, can_ko=True, wins_game=True),
    AttackPlan(plan_type="boss_ko", plan_score=600, can_ko=True, needs_boss=True),
    AttackPlan(plan_type="active_attack", plan_score=80),
]
s_ko = summarize_attack_plans(plans_ko)
check("KO: plan_count=3", s_ko["plan_count"] == 3)
check("KO: best_plan_type=winning_ko", s_ko["best_plan_type"] == "winning_ko")
check("KO: has_winning_ko", s_ko["has_winning_ko"])
check("KO: has_boss_ko", s_ko["has_boss_ko"])
check("KO: not has_active_ko", not s_ko["has_active_ko"])
check("KO: top_plan_types", s_ko["top_plan_types"] == ["winning_ko", "boss_ko", "active_attack"])

# zero_damage_escape + bench
plans_zd = [
    AttackPlan(plan_type="zero_damage_escape", plan_score=200, needs_switch=True),
    AttackPlan(plan_type="voltorb_charge", plan_score=100, needs_energy=True),
]
s_zd = summarize_attack_plans(plans_zd)
check("ZD: has_zero_damage_escape", s_zd["has_zero_damage_escape"])
check("ZD: has_bench_attacker (voltorb_charge)", s_zd["has_bench_attacker"])

# ===================================================================
print("\n--- diagnose_attack_plan_choice ---")

state = {"active_pokemon": {"card_id": "269"}, "your_index": 0,
         "opponent": {"bench": []}}

# Matching attack
atk_action = {"type": 13, "attackId": 1}
plans_match = [
    AttackPlan(plan_type="winning_ko", attacker_cid="269", plan_score=1050),
]
d_match = diagnose_attack_plan_choice(plans_match, atk_action, state)
check("Match: best_plan_type=winning_ko", d_match["best_plan_type"] == "winning_ko")
check("Match: chosen_matches_best=True", d_match["chosen_matches_best"])
check("Match: missed_ko_plan=False", not d_match["missed_ko_plan"])
check("Match: missed_high_value_plan=False", not d_match["missed_high_value_plan"])

# End action with winning_ko available
end_action = {"type": 14}
d_end = diagnose_attack_plan_choice(plans_match, end_action, state)
check("End: missed_ko_plan=True", d_end["missed_ko_plan"])
check("End: missed_high_value_plan=True", d_end["missed_high_value_plan"])
check("End: end_with_plan_available in notes", "end_with_plan_available" in d_end["notes"])
check("End: missed_winning_ko in notes", "missed_winning_ko" in d_end["notes"])

# Low-score plan, end action
plans_low = [AttackPlan(plan_type="active_attack", plan_score=50)]
d_low_end = diagnose_attack_plan_choice(plans_low, end_action, state)
check("Low end: end_with_plan_available in notes", "end_with_plan_available" in d_low_end["notes"])
check("Low end: not missed_ko", not d_low_end["missed_ko_plan"])
check("Low end: not missed_hv", not d_low_end["missed_high_value_plan"])

# Retreat when boss_ko needs_boss
boss_plans = [
    AttackPlan(plan_type="boss_ko", plan_score=900, needs_boss=True, target_cid="888"),
]
retreat_action = {"type": 12}
d_retreat = diagnose_attack_plan_choice(boss_plans, retreat_action, state)
check("Boss retreat: missed_ko_plan=True", d_retreat["missed_ko_plan"])
check("Boss retreat: missed_high_value_plan=True", d_retreat["missed_high_value_plan"])

# active_ko matched
plans_ako = [AttackPlan(plan_type="active_ko", attacker_cid="269", plan_score=250)]
d_ako = diagnose_attack_plan_choice(plans_ako, atk_action, state)
check("AKO: chosen_matches_best=True", d_ako["chosen_matches_best"])
check("AKO: missed_ko_plan=False", not d_ako["missed_ko_plan"])

# chosen_matches_any but not best
plans_multi = [
    AttackPlan(plan_type="boss_ko", plan_score=600, needs_boss=True, target_cid="888"),
    AttackPlan(plan_type="active_attack", attacker_cid="269", plan_score=80),
]
d_any = diagnose_attack_plan_choice(plans_multi, atk_action, state)
check("Multi: chosen_matches_best=False (boss needs boss)", not d_any["chosen_matches_best"])
check("Multi: chosen_matches_any=True (2nd plan)", d_any["chosen_matches_any"])

# ===================================================================
print("\n--- edge cases ---")

d_empty = diagnose_attack_plan_choice([], {"type": 13}, state)
check("Empty plans: no crash", isinstance(d_empty, dict))
check("Empty plans: missed_ko=False", not d_empty["missed_ko_plan"])

d_none = diagnose_attack_plan_choice([AttackPlan(plan_type="x")], None, state)
check("None action: no crash", isinstance(d_none, dict))

# plan_matches_action still works
bonus = plan_matches_action(plans_match[0], atk_action, state)
check("plan_matches_action still works", bonus > 0)

# ===================================================================
print("\n--- energy readiness helpers ---")

check("energy count from dict", get_attached_energy_count({"energy_count": 3}) == 3)
check("energy count default 0", get_attached_energy_count({}) == 0)
check("energy req Voltorb=2", get_attack_energy_requirement("265") == 2)
check("energy req Bellibolt=4", get_attack_energy_requirement("269") == 4)
check("energy req Kilowattrel=3", get_attack_energy_requirement("271") == 3)
check("energy req unknown=None", get_attack_energy_requirement("999") is None)

check("has energy: 2/2=True", has_attack_energy({"card_id": "265", "energy_count": 2}) is True)
check("has energy: 1/2=False", has_attack_energy({"card_id": "265", "energy_count": 1}) is False)
check("has energy: unknown=None", has_attack_energy({"card_id": "999", "energy_count": 5}) is None)

# ===================================================================
print("\n--- energy readiness in plans ---")

plans_er = [
    AttackPlan(plan_type="active_ko", plan_score=250, energy_ready=True, energy_required=2, energy_attached=3),
    AttackPlan(plan_type="winning_ko", plan_score=1050, energy_ready=False, energy_required=4, energy_attached=2),
]
s_er = summarize_attack_plans(plans_er)
check("energy_ready_plans=1", s_er["energy_ready_plans"] == 1)
check("energy_not_ready_plans=1", s_er["energy_not_ready_plans"] == 1)
check("ko_plan_energy_ready=1", s_er["ko_plan_energy_ready"] == 1)
check("ko_plan_energy_not_ready=1", s_er["ko_plan_energy_not_ready"] == 1)

# diagnose with energy
plan_ko_ready = [AttackPlan(plan_type="active_ko", attacker_cid="269", plan_score=250, energy_ready=True)]
d_er = diagnose_attack_plan_choice(plan_ko_ready, {"type": 14}, state)
check("Missed KO energy ready", d_er["missed_ko_plan_energy_ready"])
check("Not missed KO energy not ready", not d_er["missed_ko_plan_energy_not_ready"])
check("best_plan_energy_ready=True", d_er["best_plan_energy_ready"] is True)

plan_ko_not = [AttackPlan(plan_type="active_ko", attacker_cid="269", plan_score=250, energy_ready=False)]
d_enr = diagnose_attack_plan_choice(plan_ko_not, {"type": 14}, state)
check("Not missed KO energy ready", not d_enr["missed_ko_plan_energy_ready"])
check("Missed KO energy not ready", d_enr["missed_ko_plan_energy_not_ready"])
check("best_plan_energy_ready=False", d_enr["best_plan_energy_ready"] is False)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
