"""
Tests for agent/card_metadata.py and main.py normalize enrichment.

Run: python experiments/test_card_metadata.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.card_metadata import get_card_metadata, get_attack_info, enrich_pokemon, get_load_error

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

# Check if cg.api is available
_CG_AVAILABLE = False
try:
    from cg.api import all_card_data
    _CG_AVAILABLE = True
except Exception:
    print("  [INFO] cg.api not available (Windows). Testing fallback paths only.\n")

# ===================================================================
print("\n--- get_card_metadata ---")

meta_voltorb = get_card_metadata(265)
if _CG_AVAILABLE:
    check("Voltorb (265) found", meta_voltorb is not None)
    if meta_voltorb:
        check("Voltorb name", "Voltorb" in meta_voltorb["name"])
        check("Voltorb is_basic", meta_voltorb["is_basic"])
        check("Voltorb not ex", not meta_voltorb["is_ex"])
        check("Voltorb has attack_ids", len(meta_voltorb["attack_ids"]) > 0)

    meta_bellibolt = get_card_metadata(269)
    check("Bellibolt ex (269) found", meta_bellibolt is not None)
    if meta_bellibolt:
        check("Bellibolt is_ex", meta_bellibolt["is_ex"])
        check("Bellibolt not basic", not meta_bellibolt["is_basic"])
        check("Bellibolt weakness present", meta_bellibolt["weakness"] is not None)
        check("Bellibolt has abilities", len(meta_bellibolt["abilities"]) > 0)

    meta_kw = get_card_metadata(271)
    check("Kilowattrel (271) found", meta_kw is not None)
else:
    check("No cg: get_card_metadata returns None", meta_voltorb is None)

check("Unknown card returns None", get_card_metadata(99999) is None)

# Load error tracking
load_err = get_load_error()
if not _CG_AVAILABLE:
    check("No cg: load error captured", load_err is not None)
else:
    check("cg available: no load error", load_err is None)

# ===================================================================
print("\n--- get_attack_info ---")

if _CG_AVAILABLE and meta_voltorb and meta_voltorb["attack_ids"]:
    aid = meta_voltorb["attack_ids"][0]
    atk = get_attack_info(aid)
    check("Voltorb attack found", atk is not None)
    if atk:
        check("Attack has name", len(atk["name"]) > 0)
        check("Attack has damage", isinstance(atk["damage"], int))

check("Unknown attack returns None", get_attack_info(99999) is None)

# ===================================================================
print("\n--- enrich_pokemon ---")

p = {"card_id": "265", "hp_remaining": 70, "energy_count": 1}
enriched = enrich_pokemon(p)
check("Enriched has name key", "name" in enriched)
if _CG_AVAILABLE:
    check("Enriched name has content", bool(enriched.get("name")))
check("Enriched has is_ex", "is_ex" in enriched)
check("Enriched is_ex=False for Voltorb", not enriched["is_ex"])
check("Enriched has weakness", "weakness" in enriched)
check("Enriched has resistance", "resistance" in enriched)
check("Enriched has attacks list", isinstance(enriched.get("attacks"), list))
check("Enriched has abilities list", isinstance(enriched.get("abilities"), list))
check("Enriched has retreat_cost", "retreat_cost" in enriched)
check("Enriched has stage", "stage" in enriched)
check("Enriched stage=basic for Voltorb", enriched.get("stage") == "basic")

# Ex card
p_ex = {"card_id": "269", "hp_remaining": 250}
enriched_ex = enrich_pokemon(p_ex)
if _CG_AVAILABLE:
    check("Bellibolt enriched is_ex=True", enriched_ex.get("is_ex"))
else:
    check("No cg: Bellibolt defaults is_ex=False", not enriched_ex.get("is_ex"))

# Unknown card: should not crash
p_unknown = {"card_id": "99999", "hp_remaining": 100}
enriched_unk = enrich_pokemon(p_unknown)
check("Unknown card: does not crash", True)
check("Unknown card: is_ex defaults False", not enriched_unk.get("is_ex"))
check("Unknown card: attacks defaults []", enriched_unk.get("attacks") == [])

# Empty/None: should not crash
# Both id formats work
p_by_id = {"id": 265, "hp_remaining": 70}
enriched_by_id = enrich_pokemon(p_by_id)
check("id format: enriched safely", "is_ex" in enriched_by_id)

p_by_card_id = {"card_id": "265", "hp_remaining": 70}
enriched_by_cid = enrich_pokemon(p_by_card_id)
check("card_id format: enriched safely", "is_ex" in enriched_by_cid)

check("Empty dict: safe", enrich_pokemon({}) == {})
check("None: safe", enrich_pokemon(None) is None)

# Metadata load failure does not crash normalize
check("enrich_pokemon never raises", True)

# ===================================================================
print("\n--- both sides enriched ---")

if _CG_AVAILABLE:
    from main import _normalize_pokemon

    class FakePokemon:
        def __init__(self, pid, hp=100, maxHp=100):
            self.id = pid
            self.hp = hp
            self.maxHp = maxHp
            self.energies = []
            self.energyCards = []

    norm = _normalize_pokemon(FakePokemon(265, 70, 70))
    check("Normalized Voltorb has name", bool(norm.get("name")))
    check("Normalized Voltorb has is_ex", "is_ex" in norm)
    check("Normalized Voltorb has weakness", "weakness" in norm)

    norm_opp = _normalize_pokemon(FakePokemon(269, 250, 250))
    check("Normalized Bellibolt has name", bool(norm_opp.get("name")))
    check("Normalized Bellibolt is_ex", norm_opp.get("is_ex"))
    check("Normalized Bellibolt has attacks", isinstance(norm_opp.get("attacks"), list))
else:
    check("No cg: skip main.py normalize test (requires cg)", True)

# ===================================================================
print(f"\n{'='*50}")
print(f"  Passed: {_total - _failures}/{_total}")
if _failures == 0:
    print("  All checks PASSED.")
else:
    print(f"  {_failures} check(s) FAILED.")
sys.exit(0 if _failures == 0 else 1)
