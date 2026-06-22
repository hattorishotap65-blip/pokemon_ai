"""
Tests for attack energy readiness.

Run: python experiments/test_energy_readiness.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.damage_predictor import _has_attack_energy, _min_attack_cost, find_alternative_attackers

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
print("\n--- _min_attack_cost ---")

check("No attacks: cost=-1", _min_attack_cost({"attacks": []}) == -1)
check("No attacks key: cost=-1", _min_attack_cost({}) == -1)

mon_1cost = {"attacks": [{"damage": 30, "energies": ["Lightning"]}]}
check("1-cost attack: cost=1", _min_attack_cost(mon_1cost) == 1)

mon_2cost = {"attacks": [{"damage": 80, "energies": ["Lightning", "Colorless"]}]}
check("2-cost attack: cost=2", _min_attack_cost(mon_2cost) == 2)

mon_multi = {"attacks": [
    {"damage": 30, "energies": ["Lightning"]},
    {"damage": 80, "energies": ["Lightning", "Lightning", "Colorless"]},
]}
check("Multi attack: min cost=1", _min_attack_cost(mon_multi) == 1)

mon_zero = {"attacks": [{"damage": 10, "energies": []}]}
check("0-cost attack: cost=0", _min_attack_cost(mon_zero) == 0)

# ===================================================================
print("\n--- _has_attack_energy ---")

# Cost 1, energy 1 -> ready
check("Cost 1, energy 1: ready",
      _has_attack_energy({"energy_count": 1, "attacks": [{"energies": ["L"]}]}))

# Cost 2, energy 1 -> not ready
check("Cost 2, energy 1: not ready",
      not _has_attack_energy({"energy_count": 1, "attacks": [{"energies": ["L", "C"]}]}))

# Cost 2, energy 2 -> ready
check("Cost 2, energy 2: ready",
      _has_attack_energy({"energy_count": 2, "attacks": [{"energies": ["L", "C"]}]}))

# Cost 3, energy 4 -> ready
check("Cost 3, energy 4: ready",
      _has_attack_energy({"energy_count": 4, "attacks": [{"energies": ["L", "L", "C"]}]}))

# No attack info: fallback to energy >= 1
check("No attacks, energy 1: fallback ready",
      _has_attack_energy({"energy_count": 1}))

check("No attacks, energy 0: fallback not ready",
      not _has_attack_energy({"energy_count": 0}))

# 0-cost attack, energy 0 -> ready
check("0-cost, energy 0: ready",
      _has_attack_energy({"energy_count": 0, "attacks": [{"energies": []}]}))

# Multi-attack: cheapest is 1, energy 1 -> ready even if expensive attack needs 3
check("Multi attack, cheapest=1, energy=1: ready",
      _has_attack_energy({"energy_count": 1, "attacks": [
          {"energies": ["L"]}, {"energies": ["L", "L", "C"]}
      ]}))

# ===================================================================
print("\n--- find_alternative_attackers energy ordering ---")

DEFENDER = {
    "card_id": "999", "name": "Wall", "is_ex": False,
    "hp_remaining": 100, "abilities": [
        {"name": "Shell", "text": "If this Pokémon would be damaged by an attack from your opponent's Pokémon ex, prevent that damage."}
    ], "attacks": [],
}

READY_MON = {
    "card_id": "265", "name": "Voltorb", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 70, "energy_count": 2,
    "attacks": [{"attack_id": 1, "damage": 60, "energies": ["Lightning", "Colorless"]}],
    "abilities": [],
}

NOT_READY_MON = {
    "card_id": "270", "name": "Wattrel", "is_ex": False,
    "energy_type": "Lightning", "hp_remaining": 60, "energy_count": 0,
    "attacks": [{"attack_id": 2, "damage": 30, "energies": ["Lightning"]}],
    "abilities": [],
}

STATE = {
    "active_pokemon": {"card_id": "269", "is_ex": True, "energy_count": 4,
                       "attacks": [{"damage": 230}], "abilities": []},
    "bench": [NOT_READY_MON, READY_MON],
    "opponent": {"active_pokemon": DEFENDER},
}

alts = find_alternative_attackers(STATE, DEFENDER)
check("Both candidates found", len(alts) == 2)
check("Ready candidate ranked first", alts[0]["energy_ready"])
check("Not-ready candidate ranked second", not alts[1]["energy_ready"])
check("Ready score > not-ready score", alts[0]["score"] > alts[1]["score"])

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
