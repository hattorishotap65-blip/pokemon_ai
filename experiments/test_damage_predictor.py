"""
Tests for agent/damage_predictor.py.

Run: python experiments/test_damage_predictor.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.damage_predictor import predict_attack_damage, format_prediction, _detect_prevent_damage_from_ex

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

# === Test data ===

CRUSTLE_ABILITIES = [
    {"name": "Protective Shell",
     "text": "If this Pokémon would be damaged by an attack from your opponent's Pokémon ex, prevent that damage."}
]

BELLIBOLT_EX = {
    "card_id": "269", "name": "Bellibolt ex", "is_ex": True,
    "energy_type": "Lightning", "hp_remaining": 250,
    "attacks": [{"attack_id": 1, "name": "Electro Blast", "damage": 230, "text": "", "energies": []}],
    "abilities": [],
}

VOLTORB = {
    "card_id": "265", "name": "Voltorb", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 70,
    "attacks": [{"attack_id": 2, "name": "Spinning Attack", "damage": 20, "text": "", "energies": []}],
    "abilities": [],
}

KILOWATTREL = {
    "card_id": "271", "name": "Kilowattrel", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 120,
    "attacks": [{"attack_id": 3, "name": "Hurricane", "damage": 70, "text": "", "energies": []}],
    "abilities": [],
}

CRUSTLE = {
    "card_id": "999", "name": "Crustle", "is_ex": False,
    "hp_remaining": 140, "weakness": "Water", "resistance": None,
    "abilities": CRUSTLE_ABILITIES, "attacks": [],
}

GENERIC_OPP = {
    "card_id": "888", "name": "Generic Mon", "is_ex": False,
    "hp_remaining": 100, "weakness": "Lightning", "resistance": "Fighting",
    "abilities": [], "attacks": [],
}

STATE = {}

# ===================================================================
print("\n--- prevent_damage_from_ex detection ---")

check("Crustle has prevent_ex", _detect_prevent_damage_from_ex(CRUSTLE))
check("Generic has no prevent_ex", not _detect_prevent_damage_from_ex(GENERIC_OPP))
check("Voltorb has no prevent_ex", not _detect_prevent_damage_from_ex(VOLTORB))

# ===================================================================
print("\n--- Bellibolt ex vs Crustle (prevent_damage_from_ex) ---")

pred_bb_cr = predict_attack_damage(BELLIBOLT_EX, CRUSTLE, STATE)
check("BB ex vs Crustle: predicted_damage=0", pred_bb_cr["predicted_damage"] == 0)
check("BB ex vs Crustle: damage_prevented", pred_bb_cr["damage_prevented"])
check("BB ex vs Crustle: can_damage=False", not pred_bb_cr["can_damage"])
check("BB ex vs Crustle: tag=prevent_damage_from_ex", "prevent_damage_from_ex" in pred_bb_cr["tags"])

# ===================================================================
print("\n--- non-ex vs Crustle (damage goes through) ---")

pred_v_cr = predict_attack_damage(VOLTORB, CRUSTLE, STATE)
check("Voltorb vs Crustle: predicted_damage>0", pred_v_cr["predicted_damage"] > 0)
check("Voltorb vs Crustle: not prevented", not pred_v_cr["damage_prevented"])

pred_kw_cr = predict_attack_damage(KILOWATTREL, CRUSTLE, STATE)
check("KW vs Crustle: predicted_damage>0", pred_kw_cr["predicted_damage"] > 0)

# ===================================================================
print("\n--- weakness ---")

pred_bb_gen = predict_attack_damage(BELLIBOLT_EX, GENERIC_OPP, STATE)
check("BB vs Generic (Lightning weak): weakness_applies", pred_bb_gen["weakness_applies"])
check("BB vs Generic: damage doubled", pred_bb_gen["predicted_damage"] == 230 * 2)
check("BB vs Generic: can_ko", pred_bb_gen["can_ko"])

# ===================================================================
print("\n--- resistance ---")

FIGHTING_ATTACKER = {
    "card_id": "777", "name": "Fighter", "is_ex": False,
    "energy_type": "Fighting", "hp_remaining": 100,
    "attacks": [{"attack_id": 4, "name": "Punch", "damage": 50, "text": "", "energies": []}],
    "abilities": [],
}

pred_fight = predict_attack_damage(FIGHTING_ATTACKER, GENERIC_OPP, STATE)
check("Fighting vs Generic (Fighting resist): resistance_applies", pred_fight["resistance_applies"])
check("Fighting vs Generic: damage reduced", pred_fight["predicted_damage"] == 50 - 30)

# ===================================================================
print("\n--- KO detection ---")

LOW_HP_OPP = {
    "card_id": "666", "name": "Weak Mon", "is_ex": False,
    "hp_remaining": 60, "weakness": None, "resistance": None,
    "abilities": [], "attacks": [],
}

pred_ko = predict_attack_damage(KILOWATTREL, LOW_HP_OPP, STATE)
check("KW vs 60HP: can_ko", pred_ko["can_ko"])
check("KW vs 60HP: predicted_damage=70", pred_ko["predicted_damage"] == 70)

HIGH_HP_OPP = {
    "card_id": "667", "name": "Tank", "is_ex": False,
    "hp_remaining": 300, "weakness": None, "resistance": None,
    "abilities": [], "attacks": [],
}
pred_no_ko = predict_attack_damage(KILOWATTREL, HIGH_HP_OPP, STATE)
check("KW vs 300HP: not can_ko", not pred_no_ko["can_ko"])

# ===================================================================
print("\n--- format_prediction ---")

fmt = format_prediction(pred_bb_cr)
check("Format contains predicted_damage=0", "predicted_damage=0" in fmt)
check("Format contains damage_prevented", "damage_prevented" in fmt)
check("Format starts with damage_predictor:", fmt.startswith("damage_predictor:"))

# ===================================================================
print("\n--- edge cases ---")

check("None attacker: safe", predict_attack_damage(None, GENERIC_OPP, STATE)["predicted_damage"] == 0)
check("None defender: safe", predict_attack_damage(BELLIBOLT_EX, None, STATE)["predicted_damage"] == 0)
check("Empty dicts: safe", predict_attack_damage({}, {}, {})["predicted_damage"] == 0)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
