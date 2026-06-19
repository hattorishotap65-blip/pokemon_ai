"""
Tests for score_voltorb_attack() and score_voltorb_safety_penalty().

Cases per spec:
  Case 1: Voltorb active, 2 energy, attack avail, 3 lightning -> high attack score
  Case 2: Voltorb active, 2 energy, attack avail, 5 lightning -> very high, KO bonus
  Case 3: Energy attach to Voltorb: 1st=+60, 2nd=+120, 3rd=-40
  Case 4: Safety penalty: end/retreat -1000, ability -80 when attack available

Run: python experiments/test_voltorb_attack.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.ionos_rules import (
    score_voltorb_attack, score_voltorb_safety_penalty,
    score_energy_attachment, score_bellibolt_energy_attach,
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
# Fixtures
# ---------------------------------------------------------------------------

def _atk_opt():
    return {"type": 13, "attackId": 999, "resolved_card_id": None}

def _end_opt():
    return {"type": 14, "resolved_card_id": None}

def _retreat_opt():
    return {"type": 12, "resolved_card_id": None}

def _ability_opt(cid="269"):
    return {"type": 10, "resolved_card_id": cid}

def _select(*opts):
    return {"option": list(opts)}

def _bench_iono(cid, energy):
    return {"card_id": cid, "energy_count": energy, "energy_types": ["4"] * energy}

def _state(active_cid="265", active_energy=2, bench=None, opp_hp=100):
    return {
        "active_pokemon": {
            "card_id": active_cid,
            "energy_count": active_energy,
            "hp_remaining": 70,
            "energy_types": ["4"] * active_energy,
        },
        "bench": bench or [],
        "hand": [],
        "hand_count": 3,
        "prizes_remaining": 4,
        "opponent": {
            "active_pokemon": {"card_id": "99", "hp_remaining": opp_hp},
            "prizes_remaining": 4,
        },
        "energyAttached": False,
    }


ATK = _atk_opt()
END = _end_opt()
RET = _retreat_opt()
ABILITY = _ability_opt("269")

SELECT_W_ATK  = _select(ATK, ABILITY, END, RET)
SELECT_NO_ATK = _select(ABILITY, END, RET)


# ---------------------------------------------------------------------------
# Case 1: Voltorb, 2 energy, 3 lightning total -> high attack score
# ---------------------------------------------------------------------------
print("\n--- Case 1: Voltorb attack (3 lightning) ---")

# Voltorb active (2 energy) + Tadbulb bench (1 energy) = 3 lightning
state1 = _state("265", 2, bench=[_bench_iono("268", 1)])
# damage = 20 + 20*3 = 80; score = 180 + 80*0.8 + 40 = 284
s1, r1 = score_voltorb_attack(ATK, state1, SELECT_W_ATK)
check("Attack score >= 250",                   s1 >= 250.0)
check("Reason has voltorb_legal_attack",       "voltorb_legal_attack" in r1)
check("Reason has voltorb_scaling_damage",     "voltorb_scaling_damage" in r1)
check("Reason has voltorb_good_energy_count",  "voltorb_good_energy_count" in r1)


# ---------------------------------------------------------------------------
# Case 2: 5 lightning total, KO possible
# ---------------------------------------------------------------------------
print("\n--- Case 2: Voltorb attack (5 lightning, KO) ---")

# 2 on Voltorb + 2 Tadbulb + 1 Wattrel = 5 lightning; damage = 20+20*5 = 120
state2 = _state("265", 2, bench=[_bench_iono("268", 2), _bench_iono("270", 1)], opp_hp=100)
s2, r2 = score_voltorb_attack(ATK, state2, SELECT_W_ATK)
check("Attack score >= 400",                      s2 >= 400.0)
check("Reason has voltorb_very_high_energy_count", "voltorb_very_high_energy_count" in r2)
check("Reason has voltorb_can_ko",                 "voltorb_can_ko" in r2)


# ---------------------------------------------------------------------------
# Case 3: Non-Voltorb active -> returns 0
# ---------------------------------------------------------------------------
print("\n--- Case 3: non-Voltorb active ---")

state3 = _state("269", 4)
s3, _ = score_voltorb_attack(ATK, state3, SELECT_W_ATK)
check("Non-Voltorb returns 0", s3 == 0.0)

s3b, _ = score_voltorb_attack(END, state1, SELECT_W_ATK)
check("Non-attack option returns 0", s3b == 0.0)


# ---------------------------------------------------------------------------
# Case 4: Safety penalty — end/retreat/ability when Voltorb + attack
# ---------------------------------------------------------------------------
print("\n--- Case 4: Safety penalty ---")

sp_end, sr_end = score_voltorb_safety_penalty(END, state1, SELECT_W_ATK)
check("End penalty -1000",          sp_end == -1000.0)
check("Reason avoid_end_when_*",    "voltorb_avoid_end_when_attack_available" in sr_end)

sp_ret, sr_ret = score_voltorb_safety_penalty(RET, state1, SELECT_W_ATK)
check("Retreat penalty -1000",      sp_ret == -1000.0)
check("Reason avoid_retreat_when_*","voltorb_avoid_retreat_when_attack_available" in sr_ret)

sp_ab, sr_ab = score_voltorb_safety_penalty(ABILITY, state1, SELECT_W_ATK)
check("Ability penalty -80",        sp_ab == -80.0)
check("Reason avoid_optional_ab",   "voltorb_attack_available_avoid_optional_ability" in sr_ab)

# No attack available -> no penalty
sp_no, _ = score_voltorb_safety_penalty(END, state1, SELECT_NO_ATK)
check("No penalty when no attack",  sp_no == 0.0)

# Non-Voltorb active -> no penalty
sp_nv, _ = score_voltorb_safety_penalty(END, state3, SELECT_W_ATK)
check("No penalty non-Voltorb",     sp_nv == 0.0)


# ---------------------------------------------------------------------------
# Case 5: Energy attachment values for Voltorb
# ---------------------------------------------------------------------------
print("\n--- Case 5: Energy attachment to Voltorb ---")

st_e = _state("265", 0)

# Normal mode
s_first, r_first = score_energy_attachment("4", "265", st_e, target_energy=0)
check("First energy score >= 60",   s_first >= 60.0)
check("Reason voltorb_first_energy","voltorb_first_energy" in r_first)

s_second, r_second = score_energy_attachment("4", "265", st_e, target_energy=1)
check("Second energy score >= 120", s_second >= 120.0)
check("Reason voltorb_enable_attack", "voltorb_enable_attack" in r_second)

s_over, r_over = score_energy_attachment("4", "265", st_e, target_energy=2)
check("Third+ energy score <= -30", s_over <= -30.0)
check("Reason voltorb_over_attach", "voltorb_over_attach" in r_over)

# Bellibolt engine mode
s_be_first, r_be_first = score_bellibolt_energy_attach("4", "265", st_e, target_energy=0)
check("Engine first energy >= 60",  s_be_first >= 60.0)
check("Engine reason first_energy", "voltorb_first_energy" in r_be_first)

s_be_second, r_be_second = score_bellibolt_energy_attach("4", "265", st_e, target_energy=1)
check("Engine second energy >= 120",s_be_second >= 120.0)

s_be_over, _ = score_bellibolt_energy_attach("4", "265", st_e, target_energy=2)
check("Engine third+ energy <= -30",s_be_over <= -30.0)


# ---------------------------------------------------------------------------
# Case 6: Attack beats Bellibolt ability when Voltorb is active
# ---------------------------------------------------------------------------
print("\n--- Case 6: Attack vs Bellibolt ability (Voltorb active) ---")

# Voltorb active, 2 energy, 2 lightning total -> damage=60, atk_score=180+48+0 = 228
state6 = _state("265", 2)
atk_s, _ = score_voltorb_attack(ATK, state6, SELECT_W_ATK)
ab_pen, _ = score_voltorb_safety_penalty(ABILITY, state6, SELECT_W_ATK)
check("Attack score > 0",           atk_s > 0.0)
check("Ability penalized -80",      ab_pen == -80.0)
check("Net: attack clearly wins over ability penalty",
      atk_s > abs(ab_pen))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = 27
print(f"\n{'='*50}")
print(f"  Passed: {total - _failures}/{total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
