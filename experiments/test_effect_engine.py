"""
Verification checks for effect_engine.py and related scoring rules.

Checks:
  1. type=13 + attackId  -&gt; is_attack_option() True
  2. type=12             -&gt; is_retreat_option() True, is_attack_option() False
  3. Retreat is heavily penalized when attack is available
  4. Voltorb damage increases with Lightning Energy on Iono's Pokemon
  5. Bellibolt ex Ability scores high when Lightning in hand and Bellibolt < 4 energy
  6. Poke Pad cannot target Bellibolt ex (excluded_targets)
  7. Canari can target all Lightning Pokemon in this deck
  8. Poffin can target Voltorb, Tadbulb, and Wattrel

Run: python experiments/test_effect_engine.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.effect_engine import (
    load_card_effects, get_card_effect, is_attack_option, is_ability_option,
    is_retreat_option, is_end_option, estimate_attack_damage,
    count_lightning_on_iono_pokemon,
)
from agent.ionos_rules import score_bonus, _BELLIBOLT_ATTACK_ENERGY_REQ

PASS = "[PASS]"
FAIL = "[FAIL]"

def check(label: str, condition: bool):
    status = PASS if condition else FAIL
    print(f"  {status}  {label}")
    if not condition:
        global _failures
        _failures += 1

_failures = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(active_cid="265", active_energy=2, bench=None, hand=None):
    """Minimal state dict for scoring tests."""
    return {
        "active_pokemon": {"card_id": active_cid, "energy_count": active_energy,
                           "hp_remaining": 70, "energy_types": ["4"] * active_energy},
        "bench": bench or [],
        "hand": hand or [],
        "opponent": {"active_pokemon": {"card_id": "269", "hp_remaining": 200},
                     "prizes_remaining": 6},
        "prizes_remaining": 6,
        "energyAttached": False,
    }


def _make_iono_bench(cid: str, energy: int) -> dict:
    return {"card_id": cid, "energy_count": energy, "energy_types": ["4"] * energy}


# ---------------------------------------------------------------------------
# Check 1 & 2: Option type classification
# ---------------------------------------------------------------------------
print("\n--- Option type classification ---")

atk_opt     = {"type": 13, "attackId": 368}
atk_no_id   = {"type": 13, "attackId": None}
retreat_opt = {"type": 12}
ability_opt = {"type": 10, "cardId": "269"}
end_opt     = {"type": 14}

check("type=13 + attackId  -&gt; is_attack_option True",  is_attack_option(atk_opt))
check("type=13, attackId=None -&gt; is_attack_option False", not is_attack_option(atk_no_id))
check("type=12             -&gt; is_retreat_option True",  is_retreat_option(retreat_opt))
check("type=12             -&gt; is_attack_option False",  not is_attack_option(retreat_opt))
check("type=10             -&gt; is_ability_option True",  is_ability_option(ability_opt))
check("type=14             -&gt; is_end_option True",      is_end_option(end_opt))


# ---------------------------------------------------------------------------
# Check 3: Retreat heavily penalized when Bellibolt can attack (&gt;=4 energy)
# ---------------------------------------------------------------------------
print("\n--- Retreat suppression ---")

state_bellibolt_ready = _make_state(active_cid="269", active_energy=4)
retreat_action = {"type": 12, "resolved_card_id": None, "select_context": 0}
bonus_retreat, reason_retreat = score_bonus(retreat_action, state_bellibolt_ready)
check("Retreat penalized (&lt;= -700) when Bellibolt active with 4 energy",
      bonus_retreat <= -700)
check("Reason is avoid_retreat_bellibolt_can_attack",
      "avoid_retreat_bellibolt_can_attack" in reason_retreat)

state_bellibolt_3e = _make_state(active_cid="269", active_energy=3)
bonus_retreat_3, _ = score_bonus(retreat_action, state_bellibolt_3e)
check("No retreat penalty when Bellibolt has 3 energy (not yet attack-ready)",
      bonus_retreat_3 > -700)


# ---------------------------------------------------------------------------
# Check 4: Voltorb damage scales with Lightning on Iono's Pokemon
# ---------------------------------------------------------------------------
print("\n--- Voltorb damage scaling ---")

# 0 Lightning: base 20
s0 = _make_state(active_cid="265", active_energy=0,
                 bench=[_make_iono_bench("268", 0)])
dmg0, _ = estimate_attack_damage(265, s0)
check("Voltorb damage 20 when 0 Lightning in play", dmg0 == 20)

# 2 Lightning (1 on Voltorb active, 1 on bench Tadbulb)
s2 = _make_state(active_cid="265", active_energy=1,
                 bench=[_make_iono_bench("268", 1)])
dmg2, _ = estimate_attack_damage(265, s2)
check("Voltorb damage 60 when 2 Lightning in play", dmg2 == 60)

# 5 Lightning total
s5 = _make_state(active_cid="265", active_energy=2,
                 bench=[_make_iono_bench("268", 2), _make_iono_bench("270", 1)])
dmg5, _ = estimate_attack_damage(265, s5)
check("Voltorb damage 120 when 5 Lightning in play", dmg5 == 120)


# ---------------------------------------------------------------------------
# Check 5: Bellibolt ex Ability scoring
# ---------------------------------------------------------------------------
print("\n--- Bellibolt ex Ability ---")

LIGHTNING_ENERGY = "4"
# Bellibolt on bench with 0 energy, Lightning in hand -&gt; charge for attack
state_charge = _make_state(active_cid="265", active_energy=2,
                           bench=[_make_iono_bench("269", 0)],
                           hand=[LIGHTNING_ENERGY, LIGHTNING_ENERGY])
ability_action = {"type": 10, "resolved_card_id": "269", "select_context": 0}
bonus_ab, reason_ab = score_bonus(ability_action, state_charge)
check("Bellibolt Ability scored &gt;= 200 when Bellibolt < 4 energy and Lightning in hand",
      bonus_ab >= 200)
check("Reason contains 'charge_for_attack'", "charge_for_attack" in reason_ab)

# Bellibolt active with 4 energy (attack-ready), Lightning in hand
state_ready = _make_state(active_cid="269", active_energy=4,
                          hand=[LIGHTNING_ENERGY])
bonus_ready, reason_ready = score_bonus(ability_action, state_ready)
check("Bellibolt Ability reduced (&lt;= 50) when already at 4 energy",
      bonus_ready <= 50)
check("Reason contains 'voltorb_scaling'", "voltorb_scaling" in reason_ready)

# No Lightning in hand -&gt; ability useless
state_no_energy = _make_state(active_cid="269", active_energy=2, hand=[])
bonus_no_e, reason_no_e = score_bonus(ability_action, state_no_energy)
check("Bellibolt Ability scored < 20 when no Lightning in hand",
      bonus_no_e < 20)


# ---------------------------------------------------------------------------
# Check 6: Poke Pad cannot target Bellibolt ex
# ---------------------------------------------------------------------------
print("\n--- Poke Pad target restriction ---")

effects = load_card_effects()
poke_pad_data = effects.get("1152", {})
excluded = poke_pad_data.get("excluded_targets", [])
check("Poke Pad excluded_targets contains 269 (Bellibolt ex)",
      269 in excluded)
targets = poke_pad_data.get("deck_relevant_targets", [])
check("Poke Pad deck_relevant_targets does NOT contain 269",
      269 not in targets)


# ---------------------------------------------------------------------------
# Check 7: Canari can target all Lightning Pokemon
# ---------------------------------------------------------------------------
print("\n--- Canari targets ---")

canari_data = effects.get("1233", {})
canari_targets = set(canari_data.get("deck_relevant_targets", []))
check("Canari can target Voltorb (265)",     265 in canari_targets)
check("Canari can target Tadbulb (268)",     268 in canari_targets)
check("Canari can target Bellibolt ex (269)", 269 in canari_targets)
check("Canari can target Wattrel (270)",     270 in canari_targets)
check("Canari can target Kilowattrel (271)", 271 in canari_targets)


# ---------------------------------------------------------------------------
# Check 8: Poffin can target Voltorb, Tadbulb, Wattrel
# ---------------------------------------------------------------------------
print("\n--- Poffin targets ---")

poffin_data = effects.get("1086", {})
poffin_targets = set(poffin_data.get("deck_relevant_targets", []))
check("Poffin can target Voltorb (265)",  265 in poffin_targets)
check("Poffin can target Tadbulb (268)",  268 in poffin_targets)
check("Poffin can target Wattrel (270)",  270 in poffin_targets)
check("Poffin does NOT target Bellibolt ex (269)",    269 not in poffin_targets)
check("Poffin does NOT target Kilowattrel (271)",     271 not in poffin_targets)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
total = 29
print(f"  Passed: {total - _failures}/{total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
