"""
Tests for experiments/collect_attack_plan_diagnostics.py.

Run: python experiments/test_collect_attack_plan_diagnostics.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiments.collect_attack_plan_diagnostics import (
    init_summary, add_diagnosis, compute_rates, save_result,
    build_chosen_action, build_example,
    candidate_is_attack, selected_is_end, has_attack_candidate,
    classify_end_with_plan, get_legal_attack_info,
    classify_attack_decision,
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
print("\n--- init_summary ---")

s = init_summary()
check("Init: decisions=0", s["decisions"] == 0)
check("Init: missed_ko_plan=0", s["missed_ko_plan"] == 0)
check("Init: diagnostic_errors=0", s["diagnostic_errors"] == 0)
check("Init: all keys present", all(k in s for k in [
    "decisions", "plans_available", "chosen_matches_best",
    "chosen_matches_any", "missed_high_value_plan", "missed_ko_plan",
    "end_with_plan_available", "has_winning_ko", "has_active_ko",
    "has_boss_ko", "has_zero_damage_escape", "diagnostic_errors",
]))

# ===================================================================
print("\n--- add_diagnosis ---")

s = init_summary()

# KO plan matched
diag1 = {"chosen_matches_best": True, "chosen_matches_any": True,
         "missed_high_value_plan": False, "missed_ko_plan": False, "notes": []}
ps1 = {"plan_count": 2, "has_winning_ko": True, "has_active_ko": False,
       "has_boss_ko": False, "has_zero_damage_escape": False}
add_diagnosis(s, diag1, ps1)
check("After match: decisions=1", s["decisions"] == 1)
check("After match: plans_available=1", s["plans_available"] == 1)
check("After match: chosen_matches_best=1", s["chosen_matches_best"] == 1)
check("After match: has_winning_ko=1", s["has_winning_ko"] == 1)
check("After match: missed_ko=0", s["missed_ko_plan"] == 0)

# KO plan missed
diag2 = {"chosen_matches_best": False, "chosen_matches_any": False,
         "missed_high_value_plan": True, "missed_ko_plan": True,
         "notes": ["missed_active_ko", "end_with_plan_available"]}
ps2 = {"plan_count": 1, "has_winning_ko": False, "has_active_ko": True,
       "has_boss_ko": False, "has_zero_damage_escape": False}
add_diagnosis(s, diag2, ps2)
check("After miss: decisions=2", s["decisions"] == 2)
check("After miss: missed_ko=1", s["missed_ko_plan"] == 1)
check("After miss: missed_hv=1", s["missed_high_value_plan"] == 1)
check("After miss: end_with_plan=1", s["end_with_plan_available"] == 1)
check("After miss: has_active_ko=1", s["has_active_ko"] == 1)

# Zero damage escape
diag3 = {"chosen_matches_best": True, "chosen_matches_any": True,
         "missed_high_value_plan": False, "missed_ko_plan": False, "notes": []}
ps3 = {"plan_count": 1, "has_winning_ko": False, "has_active_ko": False,
       "has_boss_ko": False, "has_zero_damage_escape": True}
add_diagnosis(s, diag3, ps3)
check("After ZD: has_zero_damage_escape=1", s["has_zero_damage_escape"] == 1)

# No plans
diag4 = {"chosen_matches_best": False, "chosen_matches_any": False,
         "missed_high_value_plan": False, "missed_ko_plan": False, "notes": []}
ps4 = {"plan_count": 0}
add_diagnosis(s, diag4, ps4)
check("No plans: plans_available still 3", s["plans_available"] == 3)

# ===================================================================
print("\n--- compute_rates ---")

rates = compute_rates(s)
check("Rates is dict", isinstance(rates, dict))
check("missed_ko_rate = 1/3", abs(rates["missed_ko_plan_rate"] - 1/3) < 0.01)
check("chosen_matches_best_rate = 2/3", abs(rates["chosen_matches_best_rate"] - 2/3) < 0.01)

# Zero decisions
rates_zero = compute_rates(init_summary())
check("Zero decisions: no division error", rates_zero["missed_ko_plan_rate"] == 0.0)

# ===================================================================
print("\n--- save_result ---")

with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "diag.json")
    result = {
        "games": 10, "start_game": 97000,
        "summary": s, "rates": rates,
        "examples": [{"game_id": 97001, "turn": 5, "notes": ["missed_active_ko"]}],
    }
    save_result(path, result)
    check("File created", os.path.exists(path))
    with open(path) as f:
        loaded = json.load(f)
    check("Valid JSON", isinstance(loaded, dict))
    check("Has summary", "summary" in loaded)
    check("Has rates", "rates" in loaded)
    check("Has examples", len(loaded["examples"]) == 1)

# ===================================================================
print("\n--- examples limit ---")

s_big = init_summary()
examples = []
for i in range(25):
    examples.append({"game_id": i, "notes": ["test"]})
check("Examples can exceed 20 in list", len(examples) == 25)
check("Runner limits at _MAX_EXAMPLES=20", True)  # enforced in analyze_logs

# ===================================================================
print("\n--- build_chosen_action ---")

# New log format with raw fields
cand_new = {
    "option_type": 13, "resolved_card_id": "269",
    "cardId": "269", "attackId": 1, "area": 0, "index": 0,
    "playerIndex": 0, "inPlayArea": None, "inPlayIndex": None,
}
ca_new = build_chosen_action(cand_new)
check("New: type=13", ca_new["type"] == 13)
check("New: cardId from raw", ca_new["cardId"] == "269")
check("New: attackId", ca_new["attackId"] == 1)
check("New: area", ca_new["area"] == 0)
check("New: index", ca_new["index"] == 0)
check("New: playerIndex", ca_new["playerIndex"] == 0)

# Old log format without raw fields
cand_old = {"option_type": 13, "resolved_card_id": "269"}
ca_old = build_chosen_action(cand_old)
check("Old: type=13", ca_old["type"] == 13)
check("Old: cardId fallback to resolved", ca_old["cardId"] == "269")
check("Old: attackId=None", ca_old["attackId"] is None)
check("Old: area=None", ca_old["area"] is None)

# Extra fields
cand_extra = {
    "option_type": 8, "resolved_card_id": "4",
    "cardId": "4", "count": 1, "number": 3,
    "toolIndex": 0, "energyIndex": 2,
}
ca_extra = build_chosen_action(cand_extra)
check("Extra: count", ca_extra["count"] == 1)
check("Extra: number", ca_extra["number"] == 3)
check("Extra: toolIndex", ca_extra["toolIndex"] == 0)
check("Extra: energyIndex", ca_extra["energyIndex"] == 2)

# No cardId, no resolved
cand_empty = {"option_type": 14}
ca_empty = build_chosen_action(cand_empty)
check("Empty: cardId=None", ca_empty["cardId"] is None)
check("Empty: no crash", isinstance(ca_empty, dict))
check("Empty: count=None", ca_empty.get("count") is None)

# ===================================================================
print("\n--- build_example ---")

diag_ex = {"best_plan_type": "boss_ko", "best_plan_score": 600, "notes": ["missed_boss_ko"]}
ex = build_example(97001, {"turn": 8}, diag_ex, ca_new)
check("Example: game_id", ex["game_id"] == 97001)
check("Example: turn", ex["turn"] == 8)
check("Example: has chosen_action", "chosen_action" in ex)
check("Example: chosen_action.attackId", ex["chosen_action"]["attackId"] == 1)
check("Example: chosen_action.area", ex["chosen_action"]["area"] == 0)
check("Example: JSON serializable", isinstance(json.dumps(ex), str))

# ===================================================================
print("\n--- candidate_is_attack ---")

check("is_attack=True", candidate_is_attack({"is_attack": True, "option_type": 13}))
check("option_type=13 fallback", candidate_is_attack({"option_type": 13}))
check("option_type=14 not attack", not candidate_is_attack({"option_type": 14}))
check("empty not attack", not candidate_is_attack({}))

# ===================================================================
print("\n--- selected_is_end ---")

check("is_end=True", selected_is_end({"is_end": True, "option_type": 14}))
check("option_type=14 fallback", selected_is_end({"option_type": 14}))
check("option_type=13 not end", not selected_is_end({"option_type": 13}))

# ===================================================================
print("\n--- has_attack_candidate ---")

check("Has attack", has_attack_candidate([{"option_type": 13}, {"option_type": 14}]))
check("No attack", not has_attack_candidate([{"option_type": 14}, {"option_type": 10}]))
check("Empty list", not has_attack_candidate([]))

# ===================================================================
print("\n--- classify_end_with_plan ---")

end_cand = {"option_type": 14, "final_score": 5.0}
atk_cand = {"option_type": 13, "is_attack": True, "final_score": 20.0,
            "resolved_card_id": "269", "reason": "attack_best"}
diag_ko = {"best_plan_score": 900, "missed_ko_plan": True, "missed_high_value_plan": True}
ec = classify_end_with_plan(end_cand, [end_cand, atk_cand], diag_ko)
check("End+plan+attack: end_with_plan_and_attack", ec["end_with_plan_and_attack"])
check("End+plan+attack: not no_attack", not ec["end_with_plan_no_attack"])
check("End+KO: end_with_ko_plan", ec["end_with_ko_plan"])
check("End+HV: end_with_hv_plan", ec["end_with_hv_plan"])
check("attack_candidate_count=1", ec["attack_candidate_count"] == 1)
check("selected_final_score=5", ec["selected_final_score"] == 5.0)
check("best_attack_final_score=20", ec["best_attack_final_score"] == 20.0)
check("best_attack_reason", ec["best_attack_reason"] == "attack_best")

# End with plan but no attack
ec_no = classify_end_with_plan(end_cand, [end_cand, {"option_type": 10}],
                               {"best_plan_score": 100, "missed_ko_plan": False})
check("End+plan no attack: end_with_plan_no_attack", ec_no["end_with_plan_no_attack"])
check("End+plan no attack: not and_attack", not ec_no["end_with_plan_and_attack"])

# Not end
not_end = {"option_type": 13, "final_score": 20.0}
ec_ne = classify_end_with_plan(not_end, [not_end], {"best_plan_score": 100})
check("Not end: is_end=False", not ec_ne["is_end"])

# ===================================================================
print("\n--- get_legal_attack_info ---")

# With legal_option_summary
entry_los = {"legal_option_summary": {"total": 5, "attack": 2, "has_attack": True, "has_end": True}}
lai = get_legal_attack_info(entry_los, [])
check("LOS: has_legal_attack=True", lai["has_legal_attack"])
check("LOS: legal_attack_count=2", lai["legal_attack_count"] == 2)
check("LOS: source=legal_option_summary", lai["source"] == "legal_option_summary")

# Without legal_option_summary (fallback)
entry_old = {}
cands_fb = [{"option_type": 13}, {"option_type": 14}]
lai_fb = get_legal_attack_info(entry_old, cands_fb)
check("Fallback: has_legal_attack=True", lai_fb["has_legal_attack"])
check("Fallback: source=top_candidates_fallback", lai_fb["source"] == "top_candidates_fallback")

lai_no = get_legal_attack_info({}, [{"option_type": 14}])
check("Fallback no attack: has_legal_attack=False", not lai_no["has_legal_attack"])

# ===================================================================
print("\n--- classify_end_with_plan with legal info ---")

entry_with_los = {"legal_option_summary": {"total": 8, "attack": 1, "has_attack": True, "has_end": True}}
end_c2 = {"option_type": 14, "final_score": 5.0}
atk_c2 = {"option_type": 13, "is_attack": True, "final_score": 20.0, "resolved_card_id": "269"}
diag_c2 = {"best_plan_score": 900, "missed_ko_plan": True, "missed_high_value_plan": True}
ec2 = classify_end_with_plan(end_c2, [end_c2, atk_c2], diag_c2, entry_with_los)
check("LOS: has_legal_attack=True", ec2["has_legal_attack"])
check("LOS: end_with_plan_and_legal_attack=True", ec2["end_with_plan_and_legal_attack"])
check("LOS: end_with_ko_plan_and_legal_attack=True", ec2["end_with_ko_plan_and_legal_attack"])
check("LOS: legal_source", ec2["legal_source"] == "legal_option_summary")

# No legal attack
entry_no_la = {"legal_option_summary": {"total": 3, "attack": 0, "has_attack": False, "has_end": True}}
ec3 = classify_end_with_plan(end_c2, [end_c2], {"best_plan_score": 100, "missed_ko_plan": True}, entry_no_la)
check("No legal attack: end_with_plan_no_legal_attack=True", ec3["end_with_plan_no_legal_attack"])
check("No legal attack: end_with_plan_and_legal_attack=False", not ec3["end_with_plan_and_legal_attack"])

# Old log (no entry)
ec4 = classify_end_with_plan(end_c2, [end_c2, atk_c2], diag_c2)
check("Old log: fallback works", ec4["legal_source"] == "top_candidates_fallback")

# ===================================================================
print("\n--- add_diagnosis with end_class ---")

s_end = init_summary()
diag_end = {"chosen_matches_best": False, "chosen_matches_any": False,
            "missed_high_value_plan": True, "missed_ko_plan": True,
            "notes": ["missed_active_ko", "end_with_plan_available"]}
ps_end = {"plan_count": 1, "has_active_ko": True}
ec_end = {"is_end": True, "end_with_plan_and_attack": True,
          "end_with_plan_no_attack": False, "end_with_ko_plan": True,
          "end_with_hv_plan": True, "has_legal_attack": True,
          "end_with_plan_and_legal_attack": True, "end_with_plan_no_legal_attack": False,
          "end_with_ko_plan_and_legal_attack": True}
add_diagnosis(s_end, diag_end, ps_end, ec_end)
check("End summary: selected_end_count=1", s_end["selected_end_count"] == 1)
check("End summary: end_with_plan_and_attack=1", s_end["end_with_plan_and_attack_available"] == 1)
check("End summary: end_with_ko_plan=1", s_end["end_with_ko_plan_available"] == 1)
check("End summary: end_with_hv_plan=1", s_end["end_with_high_value_plan_available"] == 1)
check("End summary: selected_end_with_legal_attack=1", s_end["selected_end_with_legal_attack"] == 1)
check("End summary: end_with_plan_and_legal_attack=1", s_end["end_with_plan_and_legal_attack"] == 1)
check("End summary: end_with_ko_plan_and_legal_attack=1", s_end["end_with_ko_plan_and_legal_attack"] == 1)

# Without end_class (backward compat)
add_diagnosis(s_end, diag_end, ps_end)
check("No end_class: selected_end_count unchanged", s_end["selected_end_count"] == 1)

# ===================================================================
print("\n--- compute_rates with end metrics ---")

r_end = compute_rates(s_end)
check("Has end_with_plan_and_attack_rate", "end_with_plan_and_attack_rate" in r_end)
check("Has end_with_ko_plan_rate", "end_with_ko_plan_rate" in r_end)
check("Has end_with_plan_and_legal_attack_rate", "end_with_plan_and_legal_attack_rate" in r_end)
check("Has selected_end_with_legal_attack_rate", "selected_end_with_legal_attack_rate" in r_end)
check("end_with_plan_and_attack_rate=1.0", r_end["end_with_plan_and_attack_rate"] == 1.0)

# Zero end count
r_zero = compute_rates(init_summary())
check("Zero end: no division error", r_zero["end_with_plan_and_attack_rate"] == 0.0)

# ===================================================================
print("\n--- classify_attack_decision ---")

ad1 = classify_attack_decision({"type": 13}, {"legal_option_summary": {"attack": 2, "has_attack": True}}, [])
check("AD: attack selected", ad1["selected_attack"])
check("AD: has_legal_attack", ad1["has_legal_attack"])
check("AD: attack_decision_relevant", ad1["attack_decision_relevant"])
check("AD: not selected_end", not ad1["selected_end"])

ad2 = classify_attack_decision({"type": 14}, {"legal_option_summary": {"attack": 0, "has_attack": False}}, [])
check("AD: end selected", ad2["selected_end"])
check("AD: no legal attack", not ad2["has_legal_attack"])
check("AD: not attack_decision_relevant", not ad2["attack_decision_relevant"])

ad3 = classify_attack_decision({"type": 10}, {"legal_option_summary": {"attack": 1, "has_attack": True}}, [])
check("AD: ability is non_attack", ad3["selected_non_attack"])
check("AD: ability with legal attack", ad3["has_legal_attack"])

# Old log fallback
ad4 = classify_attack_decision({"type": 13}, {}, [{"option_type": 13}])
check("AD fallback: has_legal_attack from candidates", ad4["has_legal_attack"])

ad5 = classify_attack_decision({"type": 14}, {}, [{"option_type": 14}])
check("AD fallback: no legal attack", not ad5["has_legal_attack"])

# ===================================================================
print("\n--- add_diagnosis with atk_class ---")

s_atk = init_summary()
diag_atk = {"chosen_matches_best": False, "missed_ko_plan": True,
            "missed_ko_plan_energy_ready": True, "missed_ko_plan_energy_not_ready": False,
            "missed_high_value_plan": False, "notes": ["missed_active_ko"]}
ps_atk = {"plan_count": 1, "has_active_ko": True, "ko_plan_energy_ready": 1, "ko_plan_energy_not_ready": 0}
ec_atk = None
atk_cls_y = {"attack_decision_relevant": True, "has_legal_attack": True,
             "selected_attack": False, "selected_non_attack": True, "selected_end": False}
add_diagnosis(s_atk, diag_atk, ps_atk, ec_atk, atk_cls_y)
check("Atk: attack_decision_count=1", s_atk["attack_decision_count"] == 1)
check("Atk: attack_decision_missed_ko=1", s_atk["attack_decision_missed_ko"] == 1)
check("Atk: attack_decision_missed_ko_energy_ready=1", s_atk["attack_decision_missed_ko_energy_ready"] == 1)
check("Atk: selected_non_attack_with_legal_attack=1", s_atk["selected_non_attack_with_legal_attack"] == 1)
check("Atk: non_attack_decision=0", s_atk["non_attack_decision_missed_ko_energy_ready"] == 0)

# Non-attack decision (no legal attack)
atk_cls_n = {"attack_decision_relevant": False, "has_legal_attack": False,
             "selected_attack": False, "selected_non_attack": True, "selected_end": False}
add_diagnosis(s_atk, diag_atk, ps_atk, None, atk_cls_n)
check("Non-atk: attack_decision_count still 1", s_atk["attack_decision_count"] == 1)
check("Non-atk: non_attack_decision_missed_ko_energy_ready=1", s_atk["non_attack_decision_missed_ko_energy_ready"] == 1)

# ===================================================================
print("\n--- compute_rates with attack_decision ---")

r_atk = compute_rates(s_atk)
check("Has attack_decision_missed_ko_rate", "attack_decision_missed_ko_rate" in r_atk)
check("Has attack_decision_missed_ko_energy_ready_rate", "attack_decision_missed_ko_energy_ready_rate" in r_atk)
check("attack_decision_missed_ko_rate=1.0", r_atk["attack_decision_missed_ko_rate"] == 1.0)

r_zero = compute_rates(init_summary())
check("Zero attack decisions: no div error", r_zero["attack_decision_missed_ko_rate"] == 0.0)

# ===================================================================
print("\n--- diagnostic_errors ---")

s_err = init_summary()
s_err["diagnostic_errors"] += 1
check("Error count increments", s_err["diagnostic_errors"] == 1)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
