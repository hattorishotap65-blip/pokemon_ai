"""
Log analysis for Bellibolt ex behavior verification.
Reads g0100-g0149 (clean post-Bellibolt-fix logs).
"""
import json
import glob
import os
from collections import Counter

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
files   = sorted(glob.glob(os.path.join(LOG_DIR, "game_g01*.jsonl")))

NAMES = {"265": "Voltorb", "268": "Tadbulb", "270": "Wattrel",
         "271": "Kilowattrel", "269": "Bellibolt"}

reason_ctr    = Counter()
attack_ctr    = Counter()
retreat_ctr   = Counter()
ability_ctr   = Counter()
voltorb_dmgs  = []
n_entries     = 0

for fpath in files:
    for e in (json.loads(ln) for ln in open(fpath, encoding="utf-8") if ln.strip()):
        if e.get("event") == "game_end":
            continue
        n_entries += 1

        sel_ctx  = e.get("select_context")
        opt_type = e.get("select_type")
        cid      = str(e.get("resolved_card_id") or "")
        reason   = str(e.get("reason") or "")

        reason_ctr[reason] += 1

        # Attacks
        if opt_type == 13:
            attack_ctr[reason] += 1

        # Retreats
        if opt_type == 12:
            retreat_ctr[reason] += 1

        # Abilities
        if opt_type == 10:
            ability_ctr[reason] += 1

        # Voltorb damage
        dl  = e.get("deck_log") or {}
        dmg = (dl.get("voltorb") or {}).get("estimated_voltorb_damage")
        if dmg is not None:
            voltorb_dmgs.append(int(dmg))


def sep(t):
    print(f"\n{'='*60}\n  {t}\n{'='*60}")

def bar(n, total):
    w = int(n / max(total, 1) * 40)
    return "#" * w


print(f"\nFiles: {len(files)}  Entries: {n_entries}")

sep("1. ATTACK reasons (opt_type=13)")
total_atk = sum(attack_ctr.values())
for r, c in attack_ctr.most_common(20):
    print(f"  {c:5d}  {r}")
print(f"\n  Total attacks: {total_atk}")

sep("2. ABILITY reasons (opt_type=10)")
total_ab = sum(ability_ctr.values())
for r, c in ability_ctr.most_common(20):
    print(f"  {c:5d}  {r}")
print(f"\n  Total abilities: {total_ab}")

sep("3. RETREAT reasons (opt_type=12)")
total_ret = sum(retreat_ctr.values())
for r, c in retreat_ctr.most_common(20):
    print(f"  {c:5d}  {r}")
print(f"\n  Total retreats: {total_ret}")

sep("4. Bellibolt-specific reason codes (any type)")
bell_reasons = {r: c for r, c in reason_ctr.items() if "bellibolt" in r.lower()}
for r, c in sorted(bell_reasons.items(), key=lambda x: -x[1]):
    print(f"  {c:5d}  {r}")
if not bell_reasons:
    print("  (none)")

sep("5. Voltorb estimated_damage distribution")
if voltorb_dmgs:
    dmg_ctr = Counter(voltorb_dmgs)
    total_v = len(voltorb_dmgs)
    for dmg in sorted(dmg_ctr):
        b = bar(dmg_ctr[dmg], total_v)
        print(f"  {dmg:4d}: {b:<42} ({dmg_ctr[dmg]})")
    avg = sum(voltorb_dmgs) / total_v
    print(f"\n  avg={avg:.1f}  n={total_v}")
else:
    print("  (no voltorb damage data)")

sep("6. Retreat suppression codes")
supp_reasons = {r: c for r, c in reason_ctr.items() if "avoid_retreat" in r or "retreat" in r.lower()}
for r, c in sorted(supp_reasons.items(), key=lambda x: -x[1]):
    print(f"  {c:5d}  {r}")
if not supp_reasons:
    print("  (none)")
