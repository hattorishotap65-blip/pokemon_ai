"""
Tests for bench low HP liability, poffin diversity, and spread pressure.

Run: python experiments/test_bench_liability.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.ionos_rules import (
    _bench_low_hp_liability, _opp_has_spread_threat,
    _score_play_iono_basic, _score_poffin_bench,
    _VOLTORB, _TADBULB, _WATTREL,
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


def _mk_state(active_cid, bench_cids, opp_name="Generic Mon"):
    active = [{"id": int(active_cid), "card_id": active_cid, "name": f"Mon{active_cid}", "energyCards": []}]
    bench = [{"id": int(c), "card_id": c, "name": f"Mon{c}", "energyCards": []} for c in bench_cids]
    hand = []
    return {
        "players": [{"active": active, "bench": bench, "hand": hand}],
        "yourIndex": 0,
        "hand": [],
        "bench": bench,
        "prizes_remaining": 4,
        "opponent": {
            "prizes_remaining": 4,
            "active_pokemon": {"name": opp_name, "hp_remaining": 200},
            "bench": [],
        },
    }


# ===================================================================
print("\n--- bench_low_hp_liability ---")

# Bench 0: no penalty even for low HP
s0 = _mk_state(_TADBULB, [])
check("Bench 0: no penalty for Voltorb", _bench_low_hp_liability(_VOLTORB, s0) == 0.0)

# Bench has 1 Voltorb, adding second: penalty
s1 = _mk_state(_TADBULB, [_VOLTORB])
pen1 = _bench_low_hp_liability(_VOLTORB, s1)
check("1 existing Voltorb: penalty < 0", pen1 < 0)

# Bench has 2 Voltorb, adding third: bigger penalty
s2 = _mk_state(_TADBULB, [_VOLTORB, _VOLTORB])
pen2 = _bench_low_hp_liability(_VOLTORB, s2)
check("2 existing Voltorb: penalty < 1 Voltorb penalty", pen2 < pen1)

# First Voltorb (count=0): no penalty
s_first = _mk_state(_TADBULB, [_WATTREL])
check("First Voltorb: no penalty", _bench_low_hp_liability(_VOLTORB, s_first) == 0.0)

# Non-low-HP card: no penalty
check("Non-low-HP (Bellibolt): no penalty", _bench_low_hp_liability("269", s1) == 0.0)

# ===================================================================
print("\n--- opponent spread threat ---")

s_drag = _mk_state(_TADBULB, [_VOLTORB], opp_name="Dragapult ex")
check("Dragapult ex = spread threat", _opp_has_spread_threat(s_drag))

s_generic = _mk_state(_TADBULB, [_VOLTORB], opp_name="Pikachu")
check("Pikachu = no spread threat", not _opp_has_spread_threat(s_generic))

# Spread threat increases liability
pen_drag = _bench_low_hp_liability(_VOLTORB, s_drag)
pen_normal = _bench_low_hp_liability(_VOLTORB, s1)
check("Spread threat: penalty worse", pen_drag < pen_normal)

# ===================================================================
print("\n--- _score_play_iono_basic: bench 0 preserved ---")

s_empty = _mk_state(_TADBULB, [])
score_v0, _ = _score_play_iono_basic(_VOLTORB, s_empty)
check("Bench 0: Voltorb still gets high score", score_v0 > 100)

score_t0, _ = _score_play_iono_basic(_TADBULB, s_empty)
check("Bench 0: Tadbulb still gets high score", score_t0 > 100)

# ===================================================================
print("\n--- _score_play_iono_basic: duplicate penalty ---")

s_2v = _mk_state(_TADBULB, [_VOLTORB, _VOLTORB])
score_3rd_v, reason_3rd = _score_play_iono_basic(_VOLTORB, s_2v)
s_0v = _mk_state(_TADBULB, [_TADBULB])
score_1st_v, _ = _score_play_iono_basic(_VOLTORB, s_0v)
check("3rd Voltorb < 1st Voltorb", score_3rd_v < score_1st_v)

# With spread threat, even worse
s_2v_drag = _mk_state(_TADBULB, [_VOLTORB, _VOLTORB], opp_name="Dragapult ex")
score_3rd_v_drag, _ = _score_play_iono_basic(_VOLTORB, s_2v_drag)
check("3rd Voltorb + Dragapult: worse than without spread", score_3rd_v_drag < score_3rd_v)

# ===================================================================
print("\n--- poffin diversity ---")

# First of each type gets high score regardless
s_poffin = _mk_state(_TADBULB, [])
score_pv, _ = _score_poffin_bench(_VOLTORB, s_poffin)
score_pt, _ = _score_poffin_bench(_TADBULB, s_poffin)
score_pw, _ = _score_poffin_bench(_WATTREL, s_poffin)
check("Poffin: first Voltorb high", score_pv > 100)
check("Poffin: first Tadbulb high", score_pt > 100)
check("Poffin: first Wattrel high", score_pw > 50)

# Second Voltorb gets lower score than first new type
s_1v = _mk_state(_TADBULB, [_VOLTORB])
score_2nd_v, _ = _score_poffin_bench(_VOLTORB, s_1v)
score_1st_w, _ = _score_poffin_bench(_WATTREL, s_1v)
check("Poffin: first Wattrel > second Voltorb", score_1st_w > score_2nd_v)

# ===================================================================
print("\n--- bellibolt evolve line not blocked ---")

# Tadbulb should still get high priority when it's the first one
s_no_tadbulb = _mk_state(_VOLTORB, [_WATTREL])
score_tadbulb, _ = _score_play_iono_basic(_TADBULB, s_no_tadbulb)
check("First Tadbulb: high score for Bellibolt line", score_tadbulb >= 80)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
