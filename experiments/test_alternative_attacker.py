"""
Tests for alternative attacker selection (damage_predictor.find_alternative_attackers).

Run: python experiments/test_alternative_attacker.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.damage_predictor import (
    predict_attack_damage, find_alternative_attackers,
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

# === Test data ===

PREVENT_EX_DEFENDER = {
    "card_id": "999", "name": "Wall Mon", "is_ex": False,
    "hp_remaining": 140, "weakness": None, "resistance": None,
    "abilities": [{"name": "Shell",
     "text": "If this Pokémon would be damaged by an attack from your opponent's Pokémon ex, prevent that damage."}],
    "attacks": [],
}

GENERIC_DEFENDER = {
    "card_id": "888", "name": "Normal Mon", "is_ex": False,
    "hp_remaining": 100, "weakness": None, "resistance": None,
    "abilities": [], "attacks": [],
}

EX_ACTIVE = {
    "card_id": "269", "name": "Bellibolt ex", "is_ex": True,
    "energy_type": "Lightning", "hp_remaining": 250,
    "attacks": [{"attack_id": 1, "damage": 230}], "abilities": [],
}

NON_EX_BENCH_1 = {
    "card_id": "265", "name": "Voltorb", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 70, "energy_count": 2,
    "attacks": [{"attack_id": 2, "damage": 60}], "abilities": [],
}

NON_EX_BENCH_2 = {
    "card_id": "271", "name": "Kilowattrel", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 120, "energy_count": 2,
    "attacks": [{"attack_id": 3, "damage": 70}], "abilities": [],
}

EX_BENCH = {
    "card_id": "269", "name": "Bellibolt ex 2", "is_ex": True,
    "energy_type": "Lightning", "hp_remaining": 250, "energy_count": 4,
    "attacks": [{"attack_id": 1, "damage": 230}], "abilities": [],
}

NO_ENERGY_BENCH = {
    "card_id": "270", "name": "Wattrel", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 60, "energy_count": 0,
    "attacks": [{"attack_id": 4, "damage": 30}], "abilities": [],
}

# ===================================================================
print("\n--- active 0-damage, bench has alternatives ---")

STATE_ZERO_DMG = {
    "active_pokemon": EX_ACTIVE,
    "bench": [NON_EX_BENCH_1, NON_EX_BENCH_2],
    "opponent": {"active_pokemon": PREVENT_EX_DEFENDER},
}

active_pred = predict_attack_damage(EX_ACTIVE, PREVENT_EX_DEFENDER, {})
check("Active (ex) vs prevent_ex: 0 damage", active_pred["predicted_damage"] == 0)

alts = find_alternative_attackers(STATE_ZERO_DMG, PREVENT_EX_DEFENDER)
check("Alternatives found", len(alts) >= 2)
check("Best alt can_damage", alts[0]["can_damage"])
check("Best alt predicted_damage > 0", alts[0]["predicted_damage"] > 0)

# ===================================================================
print("\n--- can_ko prioritized over can_damage ---")

KO_CANDIDATE = {
    "card_id": "300", "name": "Strong Mon", "is_ex": False,
    "energy_type": "Fire", "hp_remaining": 100, "energy_count": 3,
    "attacks": [{"attack_id": 10, "damage": 200}], "abilities": [],
}
WEAK_CANDIDATE = {
    "card_id": "301", "name": "Weak Mon", "is_ex": False,
    "energy_type": "Fire", "hp_remaining": 100, "energy_count": 2,
    "attacks": [{"attack_id": 11, "damage": 30}], "abilities": [],
}

STATE_KO = {
    "active_pokemon": EX_ACTIVE,
    "bench": [WEAK_CANDIDATE, KO_CANDIDATE],
    "opponent": {"active_pokemon": PREVENT_EX_DEFENDER},
}
alts_ko = find_alternative_attackers(STATE_KO, PREVENT_EX_DEFENDER)
check("KO candidate ranked first", alts_ko[0]["card_id"] == "300")
check("KO candidate can_ko=True", alts_ko[0]["can_ko"])

# ===================================================================
print("\n--- non-ex preferred over ex ---")

STATE_EX_BENCH = {
    "active_pokemon": EX_ACTIVE,
    "bench": [EX_BENCH, NON_EX_BENCH_1],
    "opponent": {"active_pokemon": PREVENT_EX_DEFENDER},
}
alts_ex = find_alternative_attackers(STATE_EX_BENCH, PREVENT_EX_DEFENDER)
# EX_BENCH also has prevent_damage_from_ex → can't damage
# Only NON_EX_BENCH_1 should be in candidates
non_ex_alts = [a for a in alts_ex if not a["is_ex"]]
check("Non-ex candidate found", len(non_ex_alts) >= 1)

# ===================================================================
print("\n--- energy-not-ready penalized ---")

STATE_NO_ENERGY = {
    "active_pokemon": EX_ACTIVE,
    "bench": [NON_EX_BENCH_1, NO_ENERGY_BENCH],
    "opponent": {"active_pokemon": PREVENT_EX_DEFENDER},
}
alts_energy = find_alternative_attackers(STATE_NO_ENERGY, PREVENT_EX_DEFENDER)
# Both can damage, but Voltorb (energy=2) > Wattrel (energy=0)
check("Energy-ready candidate ranked higher", alts_energy[0]["energy_ready"])
no_energy = [a for a in alts_energy if not a["energy_ready"]]
check("Energy-not-ready candidate scored lower", no_energy[0]["score"] < alts_energy[0]["score"])

# ===================================================================
print("\n--- no alternatives when active damage works ---")

STATE_NORMAL = {
    "active_pokemon": EX_ACTIVE,
    "bench": [NON_EX_BENCH_1],
    "opponent": {"active_pokemon": GENERIC_DEFENDER},
}
active_pred_normal = predict_attack_damage(EX_ACTIVE, GENERIC_DEFENDER, {})
check("Active vs generic: damage > 0", active_pred_normal["predicted_damage"] > 0)

# ===================================================================
print("\n--- opponent name irrelevant ---")

SAME_ABILITY_DIFF_NAME = {
    "card_id": "777", "name": "Totally Different Mon", "is_ex": False,
    "hp_remaining": 140, "weakness": None, "resistance": None,
    "abilities": [{"name": "Shield",
     "text": "If this Pokémon would be damaged by an attack from your opponent's Pokémon ex, prevent that damage."}],
    "attacks": [],
}
STATE_DIFF_NAME = {
    "active_pokemon": EX_ACTIVE,
    "bench": [NON_EX_BENCH_1],
    "opponent": {"active_pokemon": SAME_ABILITY_DIFF_NAME},
}
alts_diff = find_alternative_attackers(STATE_DIFF_NAME, SAME_ABILITY_DIFF_NAME)
check("Same effect different name: alternatives found", len(alts_diff) >= 1)

# Same name but no prevent_ex ability: no special treatment
NO_ABILITY_SAME_NAME = {
    "card_id": "999", "name": "Wall Mon", "is_ex": False,
    "hp_remaining": 140, "abilities": [], "attacks": [],
}
active_no_prevent = predict_attack_damage(EX_ACTIVE, NO_ABILITY_SAME_NAME, {})
check("Same name no ability: damage goes through", active_no_prevent["predicted_damage"] > 0)

# ===================================================================
print("\n--- empty bench: no alternatives ---")

STATE_EMPTY = {
    "active_pokemon": EX_ACTIVE,
    "bench": [],
    "opponent": {"active_pokemon": PREVENT_EX_DEFENDER},
}
check("Empty bench: no alternatives", find_alternative_attackers(STATE_EMPTY, PREVENT_EX_DEFENDER) == [])

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
