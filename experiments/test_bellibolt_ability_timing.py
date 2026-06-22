"""
Tests for Bellibolt ability timing improvement.

Run: python experiments/test_bellibolt_ability_timing.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.ionos_rules import _score_bellibolt_ability_timing

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


def _mk(active_cid, active_energy, bench_list):
    """Helper to build state for Bellibolt ability tests."""
    bench = [{"card_id": cid, "energy_count": e, "energyCards": [{"id": "4"}]*e}
             for cid, e in bench_list]
    return {
        "active_pokemon": {"card_id": active_cid, "energy_count": active_energy,
                           "energyCards": [{"id": "4"}]*active_energy},
        "bench": bench,
        "hand": ["4"],
    }


# ===================================================================
print("\n--- enables attack (1 energy needed) ---")

# Voltorb (265) needs 2 energy, has 1 -> 1 more enables attack
s1 = _mk("265", 1, [("268", 0)])
score1, reason1 = _score_bellibolt_ability_timing(s1)
check("Voltorb needs 1 more: high score", score1 >= 280)
check("Reason mentions enables_attack", "enables_attack" in reason1)

# Kilowattrel (271) needs 3 energy, has 2 -> 1 more enables
s2 = _mk("271", 2, [("268", 0)])
score2, reason2 = _score_bellibolt_ability_timing(s2)
check("Kilowattrel needs 1 more: high score", score2 >= 280)

# Active enables attack > bench enables attack
s3 = _mk("265", 1, [("271", 1)])
score3, _ = _score_bellibolt_ability_timing(s3)
s4 = _mk("268", 0, [("265", 1)])
score4, _ = _score_bellibolt_ability_timing(s4)
check("Active enables > bench enables", score3 > score4)

# ===================================================================
print("\n--- already attack-ready: avoid over-acceleration ---")

# Voltorb has 2 energy (already attack-ready)
s5 = _mk("265", 2, [("268", 0)])
score5, reason5 = _score_bellibolt_ability_timing(s5)
# Should be lower than enables_attack case
check("Already ready Voltorb: lower than enables", score5 < 280)

# Bellibolt has 4 energy (attack-ready), no one needs energy
s6 = _mk("269", 4, [])
score6, reason6 = _score_bellibolt_ability_timing(s6)
check("All ready: low score (scaling only)", score6 <= 35)

# ===================================================================
print("\n--- Bellibolt self-charge ---")

# Bellibolt (269) needs 4 energy, has 2 -> high priority to self-charge
s7 = _mk("269", 2, [("265", 0)])
score7, reason7 = _score_bellibolt_ability_timing(s7)
check("Bellibolt self-charge: high score", score7 >= 250)
check("Bellibolt self-charge: reason", "charge_for_attack" in reason7)

# ===================================================================
print("\n--- bench candidate needs energy ---")

# Active is Tadbulb (268, not attacker), bench Voltorb needs 1 more
s8 = _mk("268", 0, [("265", 1)])
score8, reason8 = _score_bellibolt_ability_timing(s8)
check("Bench Voltorb enables attack: high", score8 >= 280)

# Bench has Voltorb needing 2 more -> progress, not enable
s9 = _mk("268", 0, [("265", 0)])
score9, reason9 = _score_bellibolt_ability_timing(s9)
check("Bench Voltorb needs 2: progress score", 80 < score9 < 280)
check("Progress reason", "progress" in reason9)

# ===================================================================
print("\n--- Voltorb extra scaling (already ready) ---")

s10 = _mk("268", 0, [("265", 3)])
score10, reason10 = _score_bellibolt_ability_timing(s10)
check("Voltorb 3 energy (extra): low scaling score", score10 <= 40)
check("Reason mentions scaling", "scaling" in reason10)

# ===================================================================
print("\n--- mixed field ---")

# Active Bellibolt (2 energy, needs 2 more), bench Voltorb (1 energy, needs 1)
s11 = _mk("269", 2, [("265", 1)])
score11, reason11 = _score_bellibolt_ability_timing(s11)
# Voltorb enables attack (280+) vs Bellibolt charge (250)
# Voltorb should win because enables_attack > charge
check("Voltorb enable > Bellibolt charge", score11 >= 280)
check("Reason is enables_attack", "enables_attack" in reason11)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
